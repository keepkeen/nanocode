from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from subprocess import run
from typing import Any, Callable
import os
import shutil

from agent_memory_os import ToolSchema
from agent_tools import (
    AuditLogger,
    BraveSearchProvider,
    ExaSearchProvider,
    SearchFilterConfig,
    SearchResultFilter,
    SecureBashTool,
    SecureWebFetchTool,
    SecureWebSearchTool,
    SecurityPolicy,
    TavilySearchProvider,
    ToolContext,
)

from nanocli.mcp_client import McpClientManager, call_server_tool, list_server_tools
from nanocli.models import McpServerConfig, ToolOptions
from nanocli.tool_runtime import RuntimeTool, SessionAwareToolExecutor, serialize_tool_output


ToolHandler = Callable[[dict[str, Any], ToolContext, Any, int], Any]


@dataclass(slots=True)
class MountedMcpServer:
    name: str
    config: McpServerConfig
    mode: str = "proxy"


@dataclass(slots=True)
class BuiltinToolCatalog:
    registry: SessionAwareToolExecutor
    tool_schemas: list[ToolSchema]
    audit_path: Path
    policy: SecurityPolicy
    notes: list[str]


def build_builtin_tool_catalog(
    *,
    workspace_root: Path,
    run_id: str,
    session_id: str | None = None,
    allow_web: bool = False,
    mounted_mcp_servers: list[MountedMcpServer] | None = None,
    mcp_manager: McpClientManager | None = None,
    extra_tools: list[RuntimeTool] | None = None,
    tool_options: ToolOptions | None = None,
) -> BuiltinToolCatalog:
    workspace_root = workspace_root.resolve()
    audit_path = workspace_root / ".nanocli" / "tool_audit" / f"{run_id}.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    tool_options = tool_options or ToolOptions()
    policy = SecurityPolicy(
        workspace_root=workspace_root,
        read_roots=[workspace_root],
        write_roots=[workspace_root],
        allow_private_network=tool_options.allow_private_network,
        allow_shell_compounds=tool_options.allow_shell_compounds,
        require_url_provenance=tool_options.require_url_provenance,
    )
    audit = AuditLogger(audit_path)
    ctx = ToolContext(session_id=session_id or run_id, cwd=workspace_root)
    bash = SecureBashTool(policy=policy, audit=audit)
    notes: list[str] = []

    tools: list[RuntimeTool] = [
        _repo_search_tool(workspace_root),
        _read_file_tool(workspace_root),
        _write_file_tool(workspace_root, policy),
        _run_checks_tool(bash, workspace_root),
    ]

    if allow_web:
        search_tool = _build_search_tool(policy=policy, audit=audit, tool_options=tool_options)
        if search_tool is not None:
            fetch_tool = SecureWebFetchTool(policy=policy, audit=audit)
            tools.extend(
                [
                    _web_search_tool(search_tool),
                    _web_fetch_tool(fetch_tool),
                ]
            )
            notes.append(f"enabled web tools with provider {search_tool.provider.provider_name}")
        else:
            notes.append(
                f"web search provider {tool_options.web_search_provider} is unavailable; missing API key or dependency"
            )

    if extra_tools:
        tools.extend(extra_tools)
        notes.append(f"loaded {len(extra_tools)} runtime skill tools")

    used_names = {tool.name for tool in tools}
    for mounted in mounted_mcp_servers or []:
        try:
            payload = list_server_tools(mounted.config, manager=mcp_manager)
            definitions = payload.get("tools", [])
            appended = 0
            for tool_definition in definitions:
                mounted_tool = _mcp_runtime_tool(
                    mounted.name,
                    mounted.config,
                    tool_definition,
                    manager=mcp_manager,
                    mode=mounted.mode,
                    used_names=used_names,
                )
                tools.append(mounted_tool)
                used_names.add(mounted_tool.name)
                appended += 1
            notes.append(f"mounted {appended} MCP tools from {mounted.name} via {mounted.mode}")
        except Exception as exc:  # pragma: no cover - transport dependent
            notes.append(f"failed to load MCP tools from {mounted.name}: {exc}")

    registry = SessionAwareToolExecutor(tools=tools, ctx=ctx)
    return BuiltinToolCatalog(
        registry=registry,
        tool_schemas=registry.schemas(),
        audit_path=audit_path,
        policy=policy,
        notes=notes,
    )


def _repo_search_tool(workspace_root: Path) -> RuntimeTool:
    def handler(arguments: dict[str, Any], _ctx: ToolContext, _state: Any, _call_count: int) -> Any:
        query = str(arguments["query"])
        path = str(arguments.get("path", "."))
        target = (workspace_root / path).resolve()
        if workspace_root not in target.parents and target != workspace_root:
            raise ValueError("path is outside workspace")
        command = ["rg", "-n", query, str(target)] if shutil.which("rg") else ["grep", "-R", "-n", query, str(target)]
        proc = run(command, cwd=workspace_root, capture_output=True, text=True, check=False)
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[:12000],
            "stderr": proc.stderr[:4000],
        }

    return RuntimeTool(
        name="search_codebase",
        description="Search the workspace for symbols, file names, or text.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=handler,
        metadata={"tool_family": "workspace"},
    )


def _read_file_tool(workspace_root: Path) -> RuntimeTool:
    def handler(arguments: dict[str, Any], _ctx: ToolContext, _state: Any, _call_count: int) -> Any:
        target = (workspace_root / str(arguments["path"])).resolve()
        if workspace_root not in target.parents and target != workspace_root:
            raise ValueError("path is outside workspace")
        text = target.read_text(encoding="utf-8")
        start = int(arguments.get("start_line", 1))
        end = int(arguments.get("end_line", 0))
        lines = text.splitlines()
        selected = lines[start - 1 :] if end <= 0 else lines[start - 1 : end]
        return {"path": str(target), "content": "\n".join(selected)}

    return RuntimeTool(
        name="read_file",
        description="Read a text file inside the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        handler=handler,
        metadata={"tool_family": "workspace"},
    )


def _write_file_tool(workspace_root: Path, policy: SecurityPolicy) -> RuntimeTool:
    def handler(arguments: dict[str, Any], _ctx: ToolContext, _state: Any, _call_count: int) -> Any:
        target = (workspace_root / str(arguments["path"])).resolve()
        if not policy.can_write_path(target):
            raise ValueError("path is outside write roots")
        content = str(arguments["content"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"path": str(target), "bytes_written": len(content.encode("utf-8"))}

    return RuntimeTool(
        name="write_file",
        description="Write a full text file inside the workspace.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        handler=handler,
        metadata={"tool_family": "workspace"},
    )


def _run_checks_tool(bash: SecureBashTool, workspace_root: Path) -> RuntimeTool:
    def handler(arguments: dict[str, Any], ctx: ToolContext, _state: Any, _call_count: int) -> Any:
        result = bash.invoke(ctx, command=str(arguments["command"]), cwd=workspace_root, allow_ask=True)
        return serialize_tool_output(result)

    return RuntimeTool(
        name="run_checks",
        description="Run a validation command inside the workspace.",
        parameters={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
        handler=handler,
        metadata={"tool_family": "workspace"},
    )


def _web_search_tool(search_tool: SecureWebSearchTool) -> RuntimeTool:
    def handler(arguments: dict[str, Any], ctx: ToolContext, state: Any, call_count: int) -> Any:
        result = search_tool.invoke(
            ctx,
            query=str(arguments["query"]),
            limit=int(arguments.get("limit", 8)),
            include_domains=list(arguments.get("include_domains") or []),
            exclude_domains=list(arguments.get("exclude_domains") or []),
            session_state=state,
            call_count=call_count,
        )
        return serialize_tool_output(result)

    return RuntimeTool(
        name="web_search",
        description="Search the web for documentation or references with result filtering and provenance tracking.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "include_domains": {"type": "array", "items": {"type": "string"}},
                "exclude_domains": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=handler,
        metadata={"tool_family": "web"},
    )


def _web_fetch_tool(fetch_tool: SecureWebFetchTool) -> RuntimeTool:
    def handler(arguments: dict[str, Any], ctx: ToolContext, state: Any, _call_count: int) -> Any:
        result = fetch_tool.invoke(
            ctx,
            url=str(arguments["url"]),
            query=str(arguments.get("query", "")),
            allow_ask=True,
            session_state=state,
        )
        return serialize_tool_output(result)

    return RuntimeTool(
        name="web_fetch",
        description="Fetch and compress a URL while enforcing provenance, policy, and evidence budgeting.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
        handler=handler,
        metadata={"tool_family": "web"},
    )


def _mcp_runtime_tool(
    server_name: str,
    server: McpServerConfig,
    tool_definition: dict[str, Any],
    *,
    manager: McpClientManager | None,
    mode: str,
    used_names: set[str],
) -> RuntimeTool:
    remote_name = str(tool_definition["name"])
    local_name = remote_name if mode == "flatten" else f"mcp__{server_name}__{remote_name}".replace(".", "_").replace("-", "_")
    if local_name in used_names:
        local_name = f"mcp__{server_name}__{remote_name}".replace(".", "_").replace("-", "_")

    def handler(arguments: dict[str, Any], _ctx: ToolContext, _state: Any, _call_count: int) -> Any:
        result = call_server_tool(server, remote_name, arguments, manager=manager)
        return result

    description = tool_definition.get("description", "") or f"MCP tool {remote_name}"
    if mode == "proxy":
        description = f"[MCP {server_name}] {description}".strip()
    return RuntimeTool(
        name=local_name,
        description=description,
        parameters=tool_definition.get("inputSchema", {"type": "object", "properties": {}, "required": []}),
        handler=handler,
        metadata={
            "tool_family": "mcp",
            "server_name": server_name,
            "remote_name": remote_name,
            "integration_mode": mode,
        },
    )


def _build_search_tool(
    *,
    policy: SecurityPolicy,
    audit: AuditLogger,
    tool_options: ToolOptions,
) -> SecureWebSearchTool | None:
    provider_name = tool_options.web_search_provider.lower().strip()
    provider_factory = {
        "tavily": TavilySearchProvider,
        "brave": BraveSearchProvider,
        "exa": ExaSearchProvider,
    }.get(provider_name)
    if provider_factory is None:
        raise ValueError(f"Unsupported web_search_provider: {tool_options.web_search_provider}")
    try:
        provider = provider_factory()
    except Exception:
        return None
    return SecureWebSearchTool(
        policy=policy,
        provider=provider,
        audit=audit,
        result_filter=SearchResultFilter(SearchFilterConfig(top_k=6)),
    )
