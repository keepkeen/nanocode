from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
from pathlib import Path
from typing import Any, Awaitable, Callable
import asyncio
import atexit
import contextlib
import json
import os
import sys
import threading
import time
import uuid

from aiohttp import ClientResponse, ClientSession, ClientTimeout, web

from mcp_polyglot.adapters.anthropic_adapter import AnthropicMcpAdapter
from mcp_polyglot.adapters.base import NativeMcpEndpoint
from mcp_polyglot.adapters.deepseek_adapter import DeepSeekAdapter as DeepSeekMcpAdapter
from mcp_polyglot.adapters.glm_adapter import GLMAdapter as GLMMcpAdapter
from mcp_polyglot.adapters.kimi_adapter import KimiAdapter as KimiMcpAdapter
from mcp_polyglot.adapters.minimax_adapter import MiniMaxFunctionAdapter as MiniMaxMcpAdapter
from mcp_polyglot.adapters.openai_adapter import OpenAIResponsesMcpAdapter
from mcp_polyglot.adapters.openai_compat_adapter import OpenAICompatibleFunctionAdapter
from mcp_polyglot.core.server import BaseMcpServer
from mcp_polyglot.core.tool import BaseMcpTool, TextContent, ToolCallResult

from .models import McpServerConfig
from .storage import LocalStateStore


JsonDict = dict[str, Any]


class McpClientError(RuntimeError):
    pass


class RemoteMcpTool(BaseMcpTool):
    def __init__(self, definition: dict[str, Any]) -> None:
        super().__init__(
            name=definition["name"],
            title=definition.get("title"),
            description=definition.get("description", ""),
            input_schema=definition.get("inputSchema", {"type": "object", "properties": {}}),
        )

    def call(self, arguments: dict[str, Any]) -> ToolCallResult:
        return ToolCallResult(
            content=[TextContent(json.dumps(arguments, ensure_ascii=False))],
            structured_content=arguments,
        )


class ExecutorMcpTool(BaseMcpTool):
    def __init__(self, name: str, description: str, input_schema: dict[str, Any], handler: Callable[[dict[str, Any]], Any]) -> None:
        super().__init__(name=name, description=description, input_schema=input_schema)
        self._handler = handler

    def call(self, arguments: dict[str, Any]) -> ToolCallResult:
        result = self._handler(arguments)
        structured = result if isinstance(result, dict) else {"value": result}
        text = json.dumps(structured, ensure_ascii=False, default=str)
        return ToolCallResult(content=[TextContent(text)], structured_content=structured)


class DynamicMcpServer(BaseMcpServer):
    def __init__(self, *, name: str = "nanocli", version: str = "0.1.0", instructions: str | None = None) -> None:
        super().__init__(name=name, version=version, protocol_version="2025-11-25", instructions=instructions)


@dataclass(slots=True)
class SessionTraceContext:
    run_id: str | None = None
    session_id: str | None = None


def _server_signature(server: McpServerConfig) -> str:
    payload = {
        "transport": server.transport,
        "url": server.url,
        "command": server.command,
        "env": server.env,
        "integration_mode": server.integration_mode,
        "native_label": server.native_label,
        "protocol_version": server.protocol_version,
        "fallback_protocol_versions": server.fallback_protocol_versions,
        "legacy_sse_fallback": server.legacy_sse_fallback,
        "headers": server.headers,
        "auth_mode": server.auth_mode,
        "auth_token_env": server.auth_token_env,
    }
    return sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def canonical_mcp_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized in {"openai", "openai_responses", "openai_chat"}:
        return "openai"
    return normalized


def provider_supports_native_mcp(provider: str, server: McpServerConfig) -> bool:
    canonical = canonical_mcp_provider(provider)
    if server.transport != "http" or not server.url:
        return False
    return canonical in {"openai", "anthropic"}


def resolve_mcp_integration_mode(server: McpServerConfig, provider: str) -> str:
    mode = server.integration_mode.strip().lower()
    if mode == "auto":
        return "native" if provider_supports_native_mcp(provider, server) else "flatten"
    if mode == "native":
        if not provider_supports_native_mcp(provider, server):
            raise McpClientError(f"MCP server {server.name} cannot use native mode with provider {provider}")
        return "native"
    if mode in {"flatten", "proxy"}:
        return mode
    raise McpClientError(f"Unsupported MCP integration mode: {server.integration_mode}")


def _jsonrpc_request(method: str, *, params: dict[str, Any] | None = None, request_id: str | None = None) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if request_id is not None:
        payload["id"] = request_id
    return payload


def _jsonrpc_response(request_id: str | int | None, *, result: Any | None = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result if result is not None else {}
    return payload


def _jsonrpc_error(code: int, message: str, *, data: Any | None = None) -> dict[str, Any]:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return error


def _sse_encode(message: dict[str, Any], *, event: str = "message", event_id: str | None = None) -> bytes:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    for line in json.dumps(message, ensure_ascii=False).splitlines() or ["{}"]:
        lines.append(f"data: {line}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")


async def _iter_sse_messages(response: ClientResponse):
    event_id: str | None = None
    event_name = "message"
    data_lines: list[str] = []
    async for raw in response.content:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if data_lines:
                payload = "\n".join(data_lines)
                try:
                    message = json.loads(payload)
                except json.JSONDecodeError:
                    message = {"event": event_name, "raw": payload}
                yield {"event": event_name, "id": event_id, "payload": message}
            event_id = None
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("id:"):
            event_id = line.split(":", 1)[1].strip()
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())


class McpAuthManager:
    def __init__(self, store: LocalStateStore | None = None) -> None:
        self.store = store

    def headers_for(self, server: McpServerConfig) -> dict[str, str]:
        headers = dict(server.headers)
        if server.auth_token_env:
            token = os.getenv(server.auth_token_env)
            if token:
                if server.auth_mode in {"bearer", "challenge"}:
                    headers.setdefault("Authorization", f"Bearer {token}")
                else:
                    headers.setdefault("X-API-Key", token)
                if self.store is not None:
                    self.store.upsert_mcp_auth_token(
                        server_name=server.name,
                        token_kind=server.auth_mode or "env",
                        token_ref=server.auth_token_env,
                        metadata={"configured": True},
                    )
        return headers

    async def handle_http_auth(self, server: McpServerConfig, response: ClientResponse) -> None:
        if response.status != 401:
            return
        challenge = response.headers.get("WWW-Authenticate", "")
        if self.store is not None:
            self.store.upsert_mcp_auth_token(
                server_name=server.name,
                token_kind="challenge",
                token_ref=challenge or "missing",
                metadata={"status": 401},
            )
        raise McpClientError(f"MCP server {server.name} rejected authentication: {challenge or 'unauthorized'}")


@dataclass
class AsyncMcpSession:
    server: McpServerConfig
    auth: McpAuthManager
    store: LocalStateStore | None = None
    workspace_root: Path | None = None
    trace_context: SessionTraceContext = field(default_factory=SessionTraceContext)
    request_counter: int = 0
    initialized: bool = False
    negotiated_protocol_version: str | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    remote_session_id: str | None = None
    status: str = "created"
    process: asyncio.subprocess.Process | None = None
    http: ClientSession | None = None
    reader_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None
    http_stream_task: asyncio.Task[None] | None = None
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pending: dict[str, asyncio.Future[dict[str, Any]]] = field(default_factory=dict)
    background_tasks: set[asyncio.Task[None]] = field(default_factory=set)
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    last_event_id: str | None = None
    mcp_session_row_id: int | None = None

    @property
    def config_signature(self) -> str:
        return _server_signature(self.server)

    async def initialize(self) -> dict[str, Any]:
        if self.initialized:
            return {"result": {"protocolVersion": self.negotiated_protocol_version, "capabilities": self.capabilities}}
        response = await self.request(
            "initialize",
            {
                "protocolVersion": self.server.protocol_version,
                "clientInfo": {"name": "nanocli", "version": "0.1.0"},
                "capabilities": self._client_capabilities(),
            },
            initialize=True,
        )
        result = response.get("result", {})
        self.negotiated_protocol_version = str(result.get("protocolVersion", self.server.protocol_version))
        self.capabilities = dict(result.get("capabilities", {}))
        self.initialized = True
        self.status = "initialized"
        self._sync_store()
        if self.store is not None and self.mcp_session_row_id is not None:
            self.store.append_mcp_capabilities(self.mcp_session_row_id, direction="server", capabilities=self.capabilities)
        await self.notify("notifications/initialized", {})
        if self.server.transport == "http" and self.server.resume_streams and self.http_stream_task is None:
            self.http_stream_task = asyncio.create_task(self._http_stream_loop())
        return response

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self.request(method, params, notification=True)

    async def ping(self) -> dict[str, Any]:
        return await self.request("ping", {})

    async def list_tools(self) -> dict[str, Any]:
        response = await self.request("tools/list", {})
        return response.get("result", response)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = await self.request("tools/call", {"name": tool_name, "arguments": arguments})
        return response.get("result", response)

    async def list_resources(self) -> dict[str, Any]:
        response = await self.request("resources/list", {})
        return response.get("result", response)

    async def read_resource(self, uri: str) -> dict[str, Any]:
        response = await self.request("resources/read", {"uri": uri})
        return response.get("result", response)

    async def list_prompts(self) -> dict[str, Any]:
        response = await self.request("prompts/list", {})
        return response.get("result", response)

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self.request("prompts/get", {"name": name, "arguments": arguments or {}})
        return response.get("result", response)

    async def inspect(self) -> dict[str, Any]:
        if not self.initialized:
            await self.initialize()
        return {
            "server_name": self.server.name,
            "transport": self.server.transport,
            "protocol_version": self.negotiated_protocol_version or self.server.protocol_version,
            "initialized": self.initialized,
            "session_identifier": self.remote_session_id,
            "capabilities": self.capabilities,
            "status": self.status,
            "config_signature": self.config_signature,
        }

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        notification: bool = False,
        initialize: bool = False,
    ) -> dict[str, Any]:
        if not initialize and not self.initialized and method != "initialize":
            await self.initialize()
        await self._ensure_transport()
        request_id = None if notification else self._next_request_id()
        payload = _jsonrpc_request(method, params=params, request_id=request_id)
        future: asyncio.Future[dict[str, Any]] | None = None
        if request_id is not None:
            future = asyncio.get_running_loop().create_future()
            self.pending[request_id] = future
        self._append_message("outbound", payload, message_type="notification" if notification else "request")
        await self._send(payload)
        if notification:
            return {}
        assert future is not None
        try:
            response = await asyncio.wait_for(future, timeout=self.server.request_timeout_seconds)
        finally:
            self.pending.pop(request_id, None)
        if "error" in response:
            raise McpClientError(str(response["error"]))
        return response

    async def close(self) -> None:
        self.stop_event.set()
        self.status = "closed"
        self._sync_store()
        for task in [self.reader_task, self.stderr_task, self.http_stream_task, *list(self.background_tasks)]:
            if task is not None:
                task.cancel()
        for task in [self.reader_task, self.stderr_task, self.http_stream_task, *list(self.background_tasks)]:
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        if self.http is not None:
            if self.remote_session_id and self.server.url:
                with contextlib.suppress(Exception):
                    await self.http.delete(
                        self.server.url,
                        headers={"Mcp-Session-Id": self.remote_session_id, "MCP-Protocol-Version": self.negotiated_protocol_version or self.server.protocol_version},
                    )
            await self.http.close()
            self.http = None
        if self.process is not None:
            self.process.terminate()
            with contextlib.suppress(ProcessLookupError):
                await asyncio.wait_for(self.process.wait(), timeout=5)
            self.process = None

    async def _ensure_transport(self) -> None:
        if self.server.transport == "stdio":
            await self._ensure_stdio_transport()
            return
        if self.server.transport == "http":
            await self._ensure_http_transport()
            return
        raise McpClientError(f"unsupported MCP transport: {self.server.transport}")

    async def _ensure_stdio_transport(self) -> None:
        if self.process is not None and self.process.returncode is None:
            return
        if not self.server.command:
            raise McpClientError(f"MCP server {self.server.name} is missing a command")
        self.process = await asyncio.create_subprocess_exec(
            *self.server.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **self.server.env},
        )
        self.status = "connected"
        self._sync_store()
        self.reader_task = asyncio.create_task(self._stdio_stdout_loop())
        self.stderr_task = asyncio.create_task(self._stdio_stderr_loop())

    async def _ensure_http_transport(self) -> None:
        if self.http is not None:
            return
        timeout = ClientTimeout(total=None, connect=self.server.connect_timeout_seconds, sock_read=self.server.request_timeout_seconds)
        self.http = ClientSession(timeout=timeout)
        self.status = "connected"
        self._sync_store()

    async def _send(self, payload: dict[str, Any]) -> None:
        async with self.write_lock:
            if self.server.transport == "stdio":
                assert self.process is not None and self.process.stdin is not None
                self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                await self.process.stdin.drain()
                return
            assert self.server.transport == "http"
            assert self.http is not None
            if not self.server.url:
                raise McpClientError(f"MCP server {self.server.name} is missing a URL")
            headers = self._http_headers()
            async with self.http.post(self.server.url, json=payload, headers=headers) as response:
                await self.auth.handle_http_auth(self.server, response)
                self._capture_http_headers(response)
                if response.content_type == "application/json":
                    message = await response.json()
                    await self._dispatch_message(message, channel="http-post")
                    return
                if response.content_type == "text/event-stream":
                    async for event in _iter_sse_messages(response):
                        self.last_event_id = event["id"] or self.last_event_id
                        self._append_stream_event(event_name=str(event["event"]), payload=event["payload"], event_id=event["id"])
                        await self._dispatch_message(event["payload"], channel="http-sse")
                    return
                raw = await response.text()
                raise McpClientError(f"unexpected MCP HTTP content type {response.content_type}: {raw[:200]}")

    async def _stdio_stdout_loop(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        while not self.stop_event.is_set():
            raw = await self.process.stdout.readline()
            if not raw:
                returncode = self.process.returncode
                self._fail_pending(
                    {
                        "code": -32001,
                        "message": "stdio MCP process exited before sending a response",
                        "data": {"returncode": returncode},
                    }
                )
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._append_stream_event(event_name="stdout-noise", payload={"raw": line})
                continue
            await self._dispatch_message(message, channel="stdio")

    async def _stdio_stderr_loop(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        while not self.stop_event.is_set():
            raw = await self.process.stderr.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                self._append_stream_event(event_name="stderr", payload={"raw": line})

    async def _http_stream_loop(self) -> None:
        if not self.server.url:
            return
        while not self.stop_event.is_set():
            try:
                assert self.http is not None
                async with self.http.get(self.server.url, headers=self._http_headers(include_accept_stream=True)) as response:
                    await self.auth.handle_http_auth(self.server, response)
                    self._capture_http_headers(response)
                    if response.content_type != "text/event-stream":
                        return
                    async for event in _iter_sse_messages(response):
                        self.last_event_id = event["id"] or self.last_event_id
                        self._append_stream_event(event_name=str(event["event"]), payload=event["payload"], event_id=event["id"])
                        await self._dispatch_message(event["payload"], channel="http-stream")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - transport dependent
                self._append_stream_event(event_name="stream-error", payload={"error": str(exc)})
                if not self.server.resume_streams:
                    return
                await asyncio.sleep(min(2, self.server.keepalive_seconds))

    async def _dispatch_message(self, message: dict[str, Any], *, channel: str) -> None:
        if not isinstance(message, dict):
            return
        message_type = "response" if "result" in message or "error" in message else "request" if "id" in message else "notification"
        self._append_message("inbound", message, message_type=message_type)
        if "id" in message and ("result" in message or "error" in message):
            future = self.pending.get(str(message["id"]))
            if future is not None and not future.done():
                future.set_result(message)
            return
        method = message.get("method")
        if not method:
            return
        if "id" in message:
            task = asyncio.create_task(self._handle_server_request(message))
            self.background_tasks.add(task)
            task.add_done_callback(self.background_tasks.discard)
        else:
            await self._handle_notification(message)

    async def _handle_notification(self, message: dict[str, Any]) -> None:
        method = str(message.get("method", ""))
        params = dict(message.get("params", {}))
        if method == "notifications/cancelled":
            request_id = str(params.get("requestId", ""))
            future = self.pending.get(request_id)
            if future is not None and not future.done():
                future.set_result({"jsonrpc": "2.0", "id": request_id, "error": _jsonrpc_error(-32800, "cancelled")})

    async def _handle_server_request(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = str(message.get("method"))
        params = dict(message.get("params", {}))
        try:
            if method == "roots/list":
                result = {"roots": self._roots_payload()}
            elif method == "sampling/createMessage":
                result = await self._handle_sampling(params)
            elif method == "elicitation/create":
                result = await self._handle_elicitation(params)
            elif method == "tasks/list":
                result = {"tasks": []}
            elif method == "tasks/get":
                result = {"task": {"id": params.get("id"), "status": "unknown"}}
            elif method == "tasks/cancel":
                result = {"cancelled": True}
            else:
                await self._send_response(request_id, error=_jsonrpc_error(-32601, f"Method not found: {method}"))
                return
            await self._send_response(request_id, result=result)
        except Exception as exc:  # pragma: no cover - defensive
            await self._send_response(request_id, error=_jsonrpc_error(-32000, "server request handler failed", data=str(exc)))

    async def _handle_sampling(self, params: dict[str, Any]) -> dict[str, Any]:
        policy = self.server.sampling_policy
        if policy == "deny":
            raise McpClientError("sampling denied by policy")
        prompt = json.dumps(params, ensure_ascii=False)
        return {"model": "nanocli-local", "stopReason": "end_turn", "content": [{"type": "text", "text": prompt[:800]}]}

    async def _handle_elicitation(self, params: dict[str, Any]) -> dict[str, Any]:
        policy = self.server.elicitation_policy
        if policy == "deny":
            raise McpClientError("elicitation denied by policy")
        form = params.get("form") or {}
        response = {field.get("name", f"field_{index}"): field.get("default", "") for index, field in enumerate(form.get("fields", []), start=1)}
        return {"submitted": True, "response": response}

    async def _send_response(self, request_id: str | int | None, *, result: Any | None = None, error: dict[str, Any] | None = None) -> None:
        await self._send(_jsonrpc_response(request_id, result=result, error=error))

    def _next_request_id(self) -> str:
        self.request_counter += 1
        return str(self.request_counter)

    def _roots_payload(self) -> list[dict[str, str]]:
        if self.server.roots_policy == "deny":
            return []
        if self.workspace_root is None:
            return []
        return [{"uri": self.workspace_root.as_uri(), "name": self.workspace_root.name or "workspace"}]

    def _client_capabilities(self) -> dict[str, Any]:
        capabilities: dict[str, Any] = {
            "roots": {"listChanged": False},
            "sampling": {},
            "elicitation": {},
            "experimental": {"tasks": {}},
        }
        capabilities.update(self.server.capabilities)
        return capabilities

    def _http_headers(self, *, include_accept_stream: bool = False) -> dict[str, str]:
        headers = {
            "MCP-Protocol-Version": self.negotiated_protocol_version or self.server.protocol_version,
            **self.auth.headers_for(self.server),
        }
        if include_accept_stream:
            headers["Accept"] = "text/event-stream"
        if self.remote_session_id:
            headers["Mcp-Session-Id"] = self.remote_session_id
        if self.last_event_id and self.server.resume_streams:
            headers["Last-Event-ID"] = self.last_event_id
        return headers

    def _capture_http_headers(self, response: ClientResponse) -> None:
        session_identifier = response.headers.get("Mcp-Session-Id")
        if session_identifier:
            self.remote_session_id = session_identifier
        if response.headers.get("MCP-Protocol-Version"):
            self.negotiated_protocol_version = response.headers["MCP-Protocol-Version"]
        self._sync_store()

    def _sync_store(self) -> None:
        if self.store is None:
            return
        self.mcp_session_row_id = self.store.upsert_mcp_session(
            server_name=self.server.name,
            transport=self.server.transport,
            config_signature=self.config_signature,
            protocol_version=self.negotiated_protocol_version or self.server.protocol_version,
            session_identifier=self.remote_session_id,
            status=self.status,
            capabilities=self.capabilities,
            metadata={"initialized": self.initialized},
        )

    def _append_message(self, direction: str, payload: dict[str, Any], *, message_type: str) -> None:
        if self.store is None:
            return
        self._sync_store()
        if self.mcp_session_row_id is None:
            return
        request_id = payload.get("id")
        self.store.append_mcp_message(
            self.mcp_session_row_id,
            direction=direction,
            message_type=message_type,
            method=payload.get("method"),
            request_id=str(request_id) if request_id is not None else None,
            payload=payload,
            run_id=self.trace_context.run_id,
            session_id=self.trace_context.session_id,
        )

    def _append_stream_event(self, *, event_name: str, payload: dict[str, Any], event_id: str | None = None) -> None:
        if self.store is None:
            return
        self._sync_store()
        if self.mcp_session_row_id is None:
            return
        self.store.append_mcp_stream_event(
            self.mcp_session_row_id,
            event_name=event_name,
            event_id=event_id,
            payload=payload,
        )

    def _fail_pending(self, error: dict[str, Any]) -> None:
        for request_id, future in list(self.pending.items()):
            if future.done():
                continue
            future.set_result({"jsonrpc": "2.0", "id": request_id, "error": error})


class _LoopThread:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, name="nanocli-mcp", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro: Awaitable[Any]) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=2)


class McpClientManager:
    def __init__(self, *, store: LocalStateStore | None = None, workspace_root: Path | None = None) -> None:
        self.store = store
        self.workspace_root = workspace_root
        self._sessions: dict[str, AsyncMcpSession] = {}
        self._loop_thread = _LoopThread()
        self.auth = McpAuthManager(store=store)
        self._trace_context = SessionTraceContext()

    def bind_context(self, *, run_id: str | None = None, session_id: str | None = None) -> "McpClientManager":
        self._trace_context = SessionTraceContext(run_id=run_id, session_id=session_id)
        return self

    def ping(self, server: McpServerConfig) -> dict[str, Any]:
        return self._loop_thread.run(self.session(server).ping())

    def list_tools(self, server: McpServerConfig) -> dict[str, Any]:
        return self._loop_thread.run(self.session(server).list_tools())

    def call_tool(self, server: McpServerConfig, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._loop_thread.run(self.session(server).call_tool(tool_name, arguments))

    def inspect(self, server: McpServerConfig) -> dict[str, Any]:
        return self._loop_thread.run(self.session(server).inspect())

    def render_payload(self, server: McpServerConfig, *, provider: str, prompt: str, model: str) -> dict[str, Any]:
        mode = resolve_mcp_integration_mode(server, provider)
        if provider == "openai":
            adapter = OpenAIResponsesMcpAdapter()
            if mode == "native" and server.url:
                return adapter.build_payload(
                    prompt=prompt,
                    model=model,
                    native_mcp=NativeMcpEndpoint(
                        server_label=server.native_label or server.name,
                        server_url=server.url,
                        server_description=f"MCP server {server.name}",
                    ),
                )
            tools = self._render_tools(server)
            return adapter.build_payload(prompt=prompt, model=model, tools=tools)
        if provider == "anthropic":
            if mode == "native":
                adapter = AnthropicMcpAdapter()
                if not server.url:
                    raise McpClientError("Anthropic MCP render requires an HTTP server URL")
                return adapter.build_payload(
                    prompt=prompt,
                    model=model,
                    native_mcp=NativeMcpEndpoint(
                        server_label=server.native_label or server.name,
                        server_url=server.url,
                    ),
                )
            return self._anthropic_tool_payload(server, prompt=prompt, model=model)
        tools = self._render_tools(server)
        adapter = self._compat_adapter(provider)
        return adapter.build_payload(prompt=prompt, model=model, tools=tools)

    def close(self) -> None:
        for session in self._sessions.values():
            self._loop_thread.run(session.close())
        self._sessions.clear()
        self._loop_thread.stop()

    def session(self, server: McpServerConfig) -> AsyncMcpSession:
        signature = _server_signature(server)
        if signature not in self._sessions:
            session = AsyncMcpSession(
                server=server,
                auth=self.auth,
                store=self.store,
                workspace_root=self.workspace_root,
            )
            self._sessions[signature] = session
        self._sessions[signature].trace_context = self._trace_context
        return self._sessions[signature]

    def _render_tools(self, server: McpServerConfig) -> list[RemoteMcpTool]:
        tools_payload = self.list_tools(server)
        definitions = tools_payload.get("tools", [])
        if not definitions and isinstance(tools_payload.get("result"), dict):
            definitions = tools_payload["result"].get("tools", [])
        return [RemoteMcpTool(tool_definition) for tool_definition in definitions]

    def _anthropic_tool_payload(self, server: McpServerConfig, *, prompt: str, model: str) -> dict[str, Any]:
        tools_payload = self.list_tools(server)
        definitions = tools_payload.get("tools", [])
        if not definitions and isinstance(tools_payload.get("result"), dict):
            definitions = tools_payload["result"].get("tools", [])
        return {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [
                {
                    "name": definition["name"],
                    "description": definition.get("description", ""),
                    "input_schema": definition.get("inputSchema", {"type": "object", "properties": {}}),
                }
                for definition in definitions
            ],
        }

    @staticmethod
    def _compat_adapter(provider: str) -> Any:
        if provider == "deepseek":
            return DeepSeekMcpAdapter()
        if provider == "glm":
            return GLMMcpAdapter()
        if provider == "kimi":
            return KimiMcpAdapter()
        if provider == "minimax":
            return MiniMaxMcpAdapter()
        adapter = OpenAICompatibleFunctionAdapter()
        adapter.provider_name = provider
        return adapter


class AsyncRuntimeMcpServer:
    def __init__(
        self,
        base_server: BaseMcpServer | None = None,
        *,
        workspace_root: Path | None = None,
        tool_executor: Any | None = None,
        tool_notes: list[str] | None = None,
        resource_provider: Callable[[], dict[str, dict[str, Any]]] | None = None,
        prompt_provider: Callable[[], dict[str, dict[str, Any]]] | None = None,
    ) -> None:
        self.base_server = base_server or self._server_from_executor(tool_executor, tool_notes=tool_notes or [])
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.protocol_version = "2025-11-25"
        self._resource_provider = resource_provider or self._default_resources
        self._prompt_provider = prompt_provider or self._default_prompts

    @staticmethod
    def _server_from_executor(tool_executor: Any | None, *, tool_notes: list[str]) -> BaseMcpServer:
        server = DynamicMcpServer(
            instructions="Use tools, prompts, and resources to inspect the current nanocli workspace."
            + ("\nNotes:\n- " + "\n- ".join(tool_notes) if tool_notes else "")
        )
        for tool in tool_executor.list_tools() if tool_executor is not None else []:
            server.register_tool(
                ExecutorMcpTool(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.parameters,
                    handler=lambda arguments, tool_name=tool.name: tool_executor.execute(tool_name, arguments),
                )
            )
        return server

    def _default_resources(self) -> dict[str, dict[str, Any]]:
        return {
            "nanocli://workspace/root": {
                "uri": "nanocli://workspace/root",
                "name": "workspace_root",
                "mimeType": "text/plain",
                "text": str(self.workspace_root),
            }
        }

    def _default_prompts(self) -> dict[str, dict[str, Any]]:
        return {
            "planner": {
                "name": "planner",
                "description": "Summarize the current project plan and execution state.",
                "messages": [{"role": "system", "content": {"type": "text", "text": "Summarize the active plan and todo frontier."}}],
            }
        }

    @property
    def prompts(self) -> dict[str, dict[str, Any]]:
        return self._prompt_provider()

    @property
    def resources(self) -> dict[str, dict[str, Any]]:
        return self._resource_provider()

    def capabilities(self) -> dict[str, Any]:
        return {
            "tools": {"listChanged": False},
            "resources": {"listChanged": False, "subscribe": False},
            "prompts": {"listChanged": False},
            "logging": {},
            "completion": {},
            "roots": {"listChanged": False},
            "experimental": {"tasks": {}},
        }

    async def handle_message(self, payload: dict[str, Any], emit: Callable[[dict[str, Any]], Awaitable[None]]) -> dict[str, Any] | None:
        method = payload.get("method")
        request_id = payload.get("id")
        params = dict(payload.get("params", {}))
        if method == "initialize":
            protocol = str(params.get("protocolVersion") or self.protocol_version)
            negotiated = protocol if protocol in {self.protocol_version, "2025-06-18"} else self.protocol_version
            return _jsonrpc_response(
                request_id,
                result={
                    "protocolVersion": negotiated,
                    "capabilities": self.capabilities(),
                    "serverInfo": {"name": "nanocli", "version": "0.1.0"},
                    "instructions": "Use tools, resources, and prompts to inspect the local workspace.",
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return _jsonrpc_response(request_id, result={})
        if method == "resources/list":
            return _jsonrpc_response(
                request_id,
                result={"resources": [{"uri": item["uri"], "name": item["name"], "mimeType": item["mimeType"]} for item in self.resources.values()]},
            )
        if method == "resources/read":
            uri = str(params.get("uri", ""))
            resource = self.resources.get(uri)
            if resource is None:
                return _jsonrpc_response(request_id, error=_jsonrpc_error(-32004, f"Unknown resource: {uri}"))
            return _jsonrpc_response(request_id, result={"contents": [resource]})
        if method == "prompts/list":
            return _jsonrpc_response(
                request_id,
                result={"prompts": [{"name": prompt["name"], "description": prompt["description"]} for prompt in self.prompts.values()]},
            )
        if method == "prompts/get":
            name = str(params.get("name", ""))
            prompt = self.prompts.get(name)
            if prompt is None:
                return _jsonrpc_response(request_id, error=_jsonrpc_error(-32004, f"Unknown prompt: {name}"))
            return _jsonrpc_response(request_id, result=prompt)
        if method == "completion/complete":
            token = str(params.get("argument", {}).get("value", ""))
            values = sorted(
                [tool["name"] for tool in self.base_server.list_tools().get("tools", [])]
                + [item["name"] for item in self.resources.values()]
                + [item["name"] for item in self.prompts.values()]
            )
            matches = [value for value in values if value.startswith(token)]
            return _jsonrpc_response(request_id, result={"completion": {"values": matches[:20]}})
        if method == "roots/list":
            return _jsonrpc_response(
                request_id,
                result={"roots": [{"uri": self.workspace_root.as_uri(), "name": self.workspace_root.name or "workspace"}]},
            )
        if method == "tasks/list":
            return _jsonrpc_response(request_id, result={"tasks": []})
        if method == "tasks/get":
            return _jsonrpc_response(request_id, result={"task": {"id": params.get("id"), "status": "unknown"}})
        if method == "tasks/cancel":
            return _jsonrpc_response(request_id, result={"cancelled": True})
        if method == "tools/call":
            await emit(_jsonrpc_request("notifications/progress", params={"progress": 0.1, "message": "starting tool call"}))
            response = self.base_server.handle_dict(payload)
            await emit(_jsonrpc_request("logging/message", params={"level": "info", "logger": "nanocli", "data": {"tool": params.get("name")}}))
            await emit(_jsonrpc_request("notifications/progress", params={"progress": 1.0, "message": "tool call completed"}))
            return response
        if method == "tools/list":
            return self.base_server.handle_dict(payload)
        return self.base_server.handle_dict(payload)


@dataclass
class _HttpServerSession:
    session_id: str
    queue: asyncio.Queue[tuple[str | None, dict[str, Any]]] = field(default_factory=asyncio.Queue)


async def _serve_stdio_async(server: AsyncRuntimeMcpServer | None = None) -> None:
    runtime_server = server or _default_runtime_mcp_server()
    lock = asyncio.Lock()

    async def emit(message: dict[str, Any]) -> None:
        async with lock:
            sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
            sys.stdout.flush()

    while True:
        raw = await asyncio.to_thread(sys.stdin.readline)
        if not raw:
            return
        if not raw.strip():
            continue
        payload = json.loads(raw)
        response = await runtime_server.handle_message(payload, emit)
        if response is not None:
            await emit(response)


async def _serve_http_async(
    host: str,
    port: int,
    server: AsyncRuntimeMcpServer | None = None,
    *,
    stop_event: asyncio.Event | None = None,
) -> None:
    runtime_server = server or _default_runtime_mcp_server()
    sessions: dict[str, _HttpServerSession] = {}
    shutdown = stop_event or asyncio.Event()

    async def get_session(request: web.Request) -> _HttpServerSession:
        session_id = request.headers.get("Mcp-Session-Id") or uuid.uuid4().hex
        session = sessions.get(session_id)
        if session is None:
            session = _HttpServerSession(session_id=session_id)
            sessions[session_id] = session
        return session

    async def handle_post(request: web.Request) -> web.Response:
        session = await get_session(request)
        payload = await request.json()

        async def emit(message: dict[str, Any]) -> None:
            await session.queue.put((None, message))

        response_payload = await runtime_server.handle_message(payload, emit)
        if response_payload is None:
            return web.json_response({}, headers={"Mcp-Session-Id": session.session_id, "MCP-Protocol-Version": runtime_server.protocol_version})
        return web.json_response(response_payload, headers={"Mcp-Session-Id": session.session_id, "MCP-Protocol-Version": runtime_server.protocol_version})

    async def handle_get(request: web.Request) -> web.StreamResponse:
        session = await get_session(request)
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Mcp-Session-Id": session.session_id,
                "MCP-Protocol-Version": runtime_server.protocol_version,
            },
        )
        await response.prepare(request)
        try:
            while True:
                event_id, message = await session.queue.get()
                await response.write(_sse_encode(message, event_id=event_id))
                await response.drain()
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await response.write_eof()
        return response

    async def handle_delete(request: web.Request) -> web.Response:
        session_id = request.headers.get("Mcp-Session-Id")
        if session_id:
            sessions.pop(session_id, None)
        return web.json_response({}, headers={"MCP-Protocol-Version": runtime_server.protocol_version})

    app = web.Application()
    app.router.add_post("/", handle_post)
    app.router.add_get("/", handle_get)
    app.router.add_delete("/", handle_delete)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port, shutdown_timeout=0.1)
    await site.start()
    try:
        await shutdown.wait()
    finally:
        await site.stop()
        await runner.cleanup()


def serve_stdio(server: AsyncRuntimeMcpServer | None = None) -> None:
    asyncio.run(_serve_stdio_async(server))


def serve_http(*, host: str = "127.0.0.1", port: int = 8765, server: AsyncRuntimeMcpServer | None = None) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_event = asyncio.Event()
    main_task = loop.create_task(_serve_http_async(host, port, server, stop_event=stop_event))
    try:
        loop.run_until_complete(main_task)
    except KeyboardInterrupt:
        stop_event.set()
        with contextlib.suppress(KeyboardInterrupt):
            loop.run_until_complete(main_task)
    finally:
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            with contextlib.suppress(Exception):
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
        asyncio.set_event_loop(None)


_GLOBAL_MANAGER = McpClientManager()
atexit.register(_GLOBAL_MANAGER.close)


def _default_runtime_mcp_server() -> AsyncRuntimeMcpServer:
    from .runtime import AgentRuntime

    return AgentRuntime().build_mcp_server()


def list_server_tools(server: McpServerConfig, *, manager: McpClientManager | None = None) -> dict[str, Any]:
    return (manager or _GLOBAL_MANAGER).list_tools(server)


def call_server_tool(
    server: McpServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    manager: McpClientManager | None = None,
) -> dict[str, Any]:
    return (manager or _GLOBAL_MANAGER).call_tool(server, tool_name, arguments)


def ping_server(server: McpServerConfig, *, manager: McpClientManager | None = None) -> dict[str, Any]:
    return (manager or _GLOBAL_MANAGER).ping(server)


def inspect_server(server: McpServerConfig, *, manager: McpClientManager | None = None) -> dict[str, Any]:
    return (manager or _GLOBAL_MANAGER).inspect(server)


def render_server_payload(
    server: McpServerConfig,
    *,
    provider: str,
    prompt: str,
    model: str,
    manager: McpClientManager | None = None,
) -> dict[str, Any]:
    return (manager or _GLOBAL_MANAGER).render_payload(server, provider=provider, prompt=prompt, model=model)
