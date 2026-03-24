from __future__ import annotations

from pathlib import Path
import asyncio
import os
import signal
import subprocess
import sys
import time

import pytest

from nanocli.mcp_client import McpClientManager
from nanocli.models import McpServerConfig, SkillsOptions, ToolOptions
from nanocli.runtime import AgentRuntime
from nanocli.skills_runtime import SkillManager
from nanocli.subagents_runtime import SubagentManager
from nanocli.tools import build_builtin_tool_catalog


def _runtime_pythonpath(repo_root: Path) -> str:
    return os.pathsep.join(
        [
            str(repo_root / "src"),
            str(repo_root / "mcp" / "mcp_polyglot"),
            str(repo_root / "memory" / "agent_memory_os_pkg"),
            str(repo_root / "agent_loop" / "plan_todo_agent"),
            str(repo_root / "tool_use"),
            str(repo_root / "tool_use" / "optimized_agent_tools"),
            str(repo_root / "auchestor" / "progressive_disclosure_bundle" / "src"),
            str(repo_root / "skills" / "multi_vendor_skills_project"),
            str(repo_root / "sub_agent" / "subagent_research"),
        ]
    )


def _write_basic_config(cwd: Path) -> None:
    (cwd / ".nanocli").mkdir(parents=True, exist_ok=True)
    (cwd / ".nanocli" / "config.toml").write_text(
        """
default_profile = "openai"

[profiles.openai]
provider = "openai_responses"
model = "gpt-5.4"
api_key_env = "OPENAI_API_KEY"

[profiles.deepseek]
provider = "deepseek"
model = "deepseek-chat"
api_key_env = "DEEPSEEK_API_KEY"
base_url = "https://api.deepseek.com"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _append_config(cwd: Path, text: str) -> None:
    config_path = cwd / ".nanocli" / "config.toml"
    config_path.write_text(config_path.read_text(encoding="utf-8") + "\n" + text.strip() + "\n", encoding="utf-8")


def test_runtime_isolates_session_memory_and_persists_planner_state(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)

    runtime = AgentRuntime(cwd=cwd)
    first = runtime.chat_turn("session alpha only", execute=False)
    second = runtime.chat_turn("session beta only", execute=False)

    runtime.mark_step_done(first.session_id, "S1")
    first_state = runtime.get_plan_state(first.session_id)
    first_memory = runtime.read_session_memory_snapshot(first.session_id)
    second_memory = runtime.read_session_memory_snapshot(second.session_id)
    project_memory = runtime.read_project_memory_snapshot()

    assert "S1" in first_state["completed_steps"]
    assert any("session alpha only" in event["content"] for event in first_memory["events"])
    assert all("session beta only" not in event["content"] for event in first_memory["events"])
    assert any("session beta only" in event["content"] for event in second_memory["events"])
    assert all("session alpha only" not in event["content"] for event in project_memory["events"])


def test_runtime_builds_project_memory_sources_candidates_and_export_models(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    (cwd / "AGENTS.md").write_text("Project rule: keep typed Python and minimal diffs.\n", encoding="utf-8")

    runtime = AgentRuntime(cwd=cwd)
    first = runtime.chat_turn("Remember that I prefer concise typed Python.", execute=False)
    second = runtime.chat_turn("Remember that I prefer concise typed Python.", execute=False)

    sources = runtime.list_project_memory_sources()
    resources = runtime.list_project_memory_resources()
    candidates = runtime.list_project_memory_candidates()
    project_memory = runtime.read_project_memory_snapshot()
    export_payload = runtime.export_plan(second.session_id, provider="deepseek")

    assert any(source["source_path"] == "AGENTS.md" for source in sources)
    assert {resource["resource_name"] for resource in resources} >= {"repo_map", "repo_overview"}
    assert any(candidate["status"] == "promoted" for candidate in candidates)
    assert any("concise typed Python" in block["text"] for block in project_memory["blocks"])
    assert any(block["metadata"].get("source_key") == "AGENTS.md" for block in project_memory["blocks"])
    assert export_payload["model"] == "deepseek-chat"
    assert first.session_id != second.session_id


def test_runtime_uses_source_backed_corroboration_for_project_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    (cwd / "AGENTS.md").write_text("Preference: concise typed Python.\n", encoding="utf-8")

    runtime = AgentRuntime(cwd=cwd)
    runtime.chat_turn("Remember that I prefer concise typed Python.", execute=False)

    candidates = runtime.list_project_memory_candidates()
    project_memory = runtime.read_project_memory_snapshot()

    assert any(candidate["status"] == "promoted" for candidate in candidates)
    assert any(
        block["kind"] == "preference" and "concise typed Python" in block["text"]
        for block in project_memory["blocks"]
    )


def test_runtime_rebuild_deactivates_stale_source_blocks_and_keeps_fragment_blocks_typed(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    agents = cwd / "AGENTS.md"
    agents.write_text(
        "# Rules\n\nPreference: concise typed Python.\n\n## Constraint\nKeep diffs minimal.\n",
        encoding="utf-8",
    )

    runtime = AgentRuntime(cwd=cwd)
    project_memory = runtime.read_project_memory_snapshot()
    active_blocks = [block for block in project_memory["blocks"] if block["active"]]

    assert any(block["metadata"].get("control_key") == "project_source:AGENTS.md" for block in active_blocks)
    assert any(block["kind"] == "preference" and block["metadata"].get("fragment_type") == "line" for block in active_blocks)
    assert any(block["kind"] == "constraint" and block["metadata"].get("fragment_type") == "heading" for block in active_blocks)

    agents.unlink()
    rebuilt = runtime.rebuild_project_memory()
    rebuilt_active = [block for block in rebuilt["blocks"] if block["active"]]

    assert rebuilt["stale_source_blocks_removed"] >= 1
    assert all(not str(block["metadata"].get("control_key", "")).startswith("project_source:AGENTS.md") for block in rebuilt_active)
    assert all("project_source:AGENTS.md" != key for key in rebuilt["source_control_keys"])


def test_skill_manager_loads_canonical_skill_py_and_instruction_only_markdown(tmp_path):
    repo = tmp_path / "repo"
    canonical_root = repo / ".nanocli" / "skills" / "planner-skill"
    markdown_root = repo / ".nanocli" / "skills" / "instruction-only-skill"
    canonical_root.mkdir(parents=True, exist_ok=True)
    markdown_root.mkdir(parents=True, exist_ok=True)

    (canonical_root / "skill.py").write_text(
        """
from multi_vendor_skills.models import SkillDefinition, ToolSpec

def echo(arguments: dict) -> dict:
    return {"echo": arguments["text"]}

SKILL = SkillDefinition(
    name="planner-skill",
    title="Planner Skill",
    description="Canonical executable skill",
    instructions="Use the echo tool when you need deterministic output.",
    tools=[
        ToolSpec(
            name="echo_tool",
            description="Echo a short text payload.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            executor=echo,
            strict=True,
        )
    ],
)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (markdown_root / "SKILL.md").write_text(
        """---
name: instruction-only-skill
description: Markdown-only fallback
---

# Instruction Only Skill

This package should be loaded without executable tools.
""",
        encoding="utf-8",
    )

    manager = SkillManager(repo, SkillsOptions(project_paths=[".nanocli/skills"]))
    catalog = manager.discover()
    runtime_tools = manager.build_runtime_tools([catalog["planner-skill"], catalog["instruction-only-skill"]])

    assert catalog["planner-skill"].instruction_only is False
    assert len(catalog["planner-skill"].tools) == 1
    assert catalog["instruction-only-skill"].instruction_only is True
    assert not catalog["instruction-only-skill"].tools
    assert [tool.name for tool in runtime_tools] == ["echo_tool"]


def test_mcp_stateful_stdio_handshake_and_render(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    pythonpath = _runtime_pythonpath(repo_root)
    server = McpServerConfig(
        name="demo",
        transport="stdio",
        command=[
            sys.executable,
            "-c",
            "from nanocli.mcp_client import serve_stdio; serve_stdio()",
        ],
        env={
            "PYTHONPATH": pythonpath,
            "XDG_CONFIG_HOME": str(tmp_path / "xdg_config"),
            "XDG_DATA_HOME": str(tmp_path / "xdg_data"),
        },
    )
    manager = McpClientManager()

    ping = manager.ping(server)
    tools = manager.list_tools(server)
    call = manager.call_tool(server, "search_codebase", {"query": "nanocli"})
    payload = manager.render_payload(server, provider="deepseek", prompt="Weather for Hangzhou", model="deepseek-chat")
    session = manager.session(server)
    assert session.initialized is True
    manager.close()

    assert "result" in ping
    assert any(tool["name"] == "search_codebase" for tool in tools["tools"])
    assert "matches" in call["structuredContent"] or "stdout" in call["structuredContent"]
    assert payload["tools"][0]["function"]["name"] == "search_codebase"


def test_mcp_render_openai_native_does_not_require_tools_listing():
    manager = McpClientManager()
    server = McpServerConfig(
        name="docs",
        transport="http",
        url="https://example.invalid/mcp",
        integration_mode="auto",
    )

    def fail_list_tools(_server):
        raise AssertionError("native render should not call tools/list")

    manager.list_tools = fail_list_tools  # type: ignore[method-assign]
    payload = manager.render_payload(server, provider="openai", prompt="Use MCP docs", model="gpt-5.4")
    manager.close()

    assert payload["tools"][0]["type"] == "mcp"
    assert payload["tools"][0]["server_label"] == "docs"


def test_mcp_render_anthropic_flatten_fallback_uses_tools_payload():
    manager = McpClientManager()
    server = McpServerConfig(
        name="docs-stdio",
        transport="stdio",
        command=["fake"],
        integration_mode="auto",
    )
    manager.list_tools = lambda _server: {  # type: ignore[method-assign]
        "tools": [
            {
                "name": "search_docs",
                "description": "Search docs",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            }
        ]
    }
    payload = manager.render_payload(server, provider="anthropic", prompt="Use docs", model="claude-sonnet-4.6")
    manager.close()

    assert payload["tools"][0]["name"] == "search_docs"
    assert payload["messages"][0]["role"] == "user"


def test_mcp_streamable_http_session_and_inspection(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    repo_root = Path(__file__).resolve().parents[1]
    pythonpath = _runtime_pythonpath(repo_root)
    env = {**os.environ, "PYTHONPATH": pythonpath}
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from nanocli.mcp_client import serve_http; serve_http(port=8876)",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    server = McpServerConfig(
        name="demo-http",
        transport="http",
        url="http://127.0.0.1:8876/",
    )
    runtime = AgentRuntime(cwd=cwd)
    manager = runtime.mcp
    try:
        deadline = time.time() + 10
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                ping = manager.ping(server)
                break
            except Exception as exc:  # pragma: no cover - readiness polling
                last_error = exc
                time.sleep(0.2)
        else:  # pragma: no cover - defensive
            pytest.skip(f"HTTP MCP server could not bind/connect in this sandbox: {last_error}")
        tools = manager.list_tools(server)
        inspect = manager.inspect(server)
        sessions = runtime.list_mcp_sessions()
        session_row = next(session for session in sessions if session["server_name"] == "demo-http")
        messages = runtime.list_mcp_messages(session_row["mcp_session_id"])
        assert "result" in ping
        assert any(tool["name"] == "search_codebase" for tool in tools["tools"])
        assert inspect["initialized"] is True
        assert inspect["protocol_version"] in {"2025-11-25", "2025-06-18"}
        assert session_row["status"] in {"initialized", "connected"}
        assert messages
    finally:
        manager.close()
        process.terminate()
        process.wait(timeout=5)


def test_runtime_compiles_native_openai_mcp_without_proxy_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    monkeypatch.setenv("MCP_TEST_TOKEN", "secret-token")
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    _append_config(
        cwd,
        """
[mcp.servers.docs]
transport = "http"
url = "https://example.com/mcp"
integration_mode = "auto"
auth_mode = "bearer"
auth_token_env = "MCP_TEST_TOKEN"
""",
    )

    runtime = AgentRuntime(cwd=cwd)
    result = runtime.run("Use the MCP docs server", execute=False)

    tools = result.provider_request["payload"]["tools"]
    assert any(tool["type"] == "mcp" and tool["server_label"] == "docs" for tool in tools)
    assert all(tool.get("name") != "mcp__docs__search" for tool in tools if isinstance(tool, dict))
    assert result.provider_request["diagnostics"]["mcp"]["native"] == ["docs"]
    assert result.provider_request["diagnostics"]["mcp"]["mounted"] == []


def test_runtime_backed_mcp_server_exposes_tools_resources_and_prompts(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)

    runtime = AgentRuntime(cwd=cwd)
    server = runtime.build_mcp_server()
    emitted: list[dict[str, object]] = []

    async def emit(message: dict[str, object]) -> None:
        emitted.append(message)

    tools = asyncio.run(server.handle_message({"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}}, emit))
    resources = asyncio.run(server.handle_message({"jsonrpc": "2.0", "id": "2", "method": "resources/list", "params": {}}, emit))
    prompts = asyncio.run(server.handle_message({"jsonrpc": "2.0", "id": "3", "method": "prompts/list", "params": {}}, emit))

    assert any(tool["name"] == "search_codebase" for tool in tools["result"]["tools"])
    assert any(resource["name"] == "project_memory" for resource in resources["result"]["resources"])
    assert any(resource["name"] == "latest_traces" for resource in resources["result"]["resources"])
    assert any(prompt["name"] == "planner" for prompt in prompts["result"]["prompts"])


def test_runtime_backed_mcp_server_reads_latest_traces_resource(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)

    runtime = AgentRuntime(cwd=cwd)
    runtime.run("Trace resource smoke", execute=False)
    server = runtime.build_mcp_server()

    async def emit(_message: dict[str, object]) -> None:
        return None

    response = asyncio.run(
        server.handle_message(
            {"jsonrpc": "2.0", "id": "4", "method": "resources/read", "params": {"uri": "nanocli://traces/latest"}},
            emit,
        )
    )
    contents = response["result"]["contents"][0]

    assert contents["name"] == "latest_traces"
    assert "Trace resource smoke" in contents["text"] or '"trace_count"' in contents["text"]


def test_builtin_catalog_uses_configured_web_search_provider(tmp_path, monkeypatch):
    class DummyBraveProvider:
        provider_name = "brave"

        def search(self, query: str, *, limit: int = 5, include_domains=None, exclude_domains=None):
            return []

    monkeypatch.setattr("nanocli.tools.builtin.BraveSearchProvider", DummyBraveProvider)
    catalog = build_builtin_tool_catalog(
        workspace_root=tmp_path,
        run_id="run-1",
        allow_web=True,
        mounted_mcp_servers=[],
        extra_tools=[],
        tool_options=ToolOptions(web_search_provider="brave"),
    )

    assert any(schema.name == "web_search" for schema in catalog.tool_schemas)
    assert any("provider brave" in note for note in catalog.notes)


def test_mcp_http_server_shutdown_is_clean(tmp_path):
    if sys.platform.startswith("win"):
        pytest.skip("signal-based shutdown smoke is only covered on Unix-like platforms")
    repo_root = Path(__file__).resolve().parents[1]
    pythonpath = _runtime_pythonpath(repo_root)
    env = {**os.environ, "PYTHONPATH": pythonpath}
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from nanocli.mcp_client import serve_http; serve_http(port=8877)",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    server = McpServerConfig(
        name="demo-http-shutdown",
        transport="http",
        url="http://127.0.0.1:8877/",
    )
    manager = McpClientManager()
    try:
        deadline = time.time() + 10
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                manager.ping(server)
                break
            except Exception as exc:  # pragma: no cover - readiness polling
                last_error = exc
                time.sleep(0.2)
        else:  # pragma: no cover - defensive
            pytest.skip(f"HTTP MCP server could not bind/connect in this sandbox: {last_error}")
        manager.close()
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=5)
    finally:
        manager.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
    assert process.returncode in {0, -signal.SIGINT, 128 + signal.SIGINT}
    assert "Traceback" not in stderr
    assert "Unhandled exception" not in stderr
    assert "InvalidStateError" not in stderr


def test_subagent_manager_exports_provider_artifacts_and_memory():
    manager = SubagentManager(max_parallel_agents=3, timeout_seconds=5)
    payload = manager.run(
        task_id="run-2",
        query="Research and review an implementation plan for the agent runtime",
        shared_context={"cwd": "/tmp/example"},
    )

    providers = {artifact["provider"] for artifact in payload["provider_artifacts"]}

    assert payload["working_memory"]["archived_summaries"] == {} or isinstance(payload["working_memory"]["archived_summaries"], dict)
    assert payload["provider_artifacts"]
    assert "deepseek" in providers
    assert "claude_code" in providers
