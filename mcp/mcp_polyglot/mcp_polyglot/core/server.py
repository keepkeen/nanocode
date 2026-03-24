from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from .protocol import JsonRpcRequest, JsonRpcResponse, make_error
from .tool import BaseMcpTool


JSON = Dict[str, Any]


@dataclass(slots=True)
class ServerInfo:
    name: str
    version: str
    title: Optional[str] = None

    def to_dict(self) -> JSON:
        payload: JSON = {"name": self.name, "version": self.version}
        if self.title:
            payload["title"] = self.title
        return payload


class BaseMcpServer:
    """
    最小可用 MCP Server 基类：
    - initialize
    - notifications/initialized
    - ping
    - tools/list
    - tools/call
    """

    def __init__(
        self,
        *,
        name: str,
        version: str = "0.1.0",
        protocol_version: str = "2025-06-18",
        instructions: Optional[str] = None,
    ) -> None:
        self.server_info = ServerInfo(name=name, version=version)
        self.protocol_version = protocol_version
        self.instructions = instructions
        self._tools: Dict[str, BaseMcpTool] = {}
        self._initialized = False

    def register_tool(self, tool: BaseMcpTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def register_tools(self, tools: Iterable[BaseMcpTool]) -> None:
        for tool in tools:
            self.register_tool(tool)

    def list_tools(self) -> JSON:
        return {"tools": [tool.to_mcp_tool_definition() for tool in self._tools.values()]}

    def call_tool(self, name: str, arguments: Optional[JSON] = None) -> JSON:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        result = self._tools[name].call(arguments or {})
        return result.to_mcp_dict()

    def capabilities(self) -> JSON:
        return {"tools": {"listChanged": False}}

    def handle_dict(self, data: JSON) -> JSON:
        request = JsonRpcRequest.from_dict(data)
        response = self.handle_request(request)
        return response.to_dict()

    def handle_request(self, request: JsonRpcRequest) -> JsonRpcResponse:
        try:
            if request.method == "initialize":
                self._initialized = True
                return JsonRpcResponse(
                    id=request.id,
                    result={
                        "protocolVersion": self.protocol_version,
                        "capabilities": self.capabilities(),
                        "serverInfo": self.server_info.to_dict(),
                        "instructions": self.instructions
                        or "Use tools/list to discover tools and tools/call to invoke them.",
                    },
                )

            if request.method == "notifications/initialized":
                self._initialized = True
                return JsonRpcResponse(id=request.id, result={})

            if request.method == "ping":
                return JsonRpcResponse(id=request.id, result={})

            if request.method == "tools/list":
                return JsonRpcResponse(id=request.id, result=self.list_tools())

            if request.method == "tools/call":
                params = request.params or {}
                name = params.get("name")
                if not name:
                    return JsonRpcResponse(
                        id=request.id,
                        error=make_error(-32602, "Missing required param: name"),
                    )
                arguments = params.get("arguments", {})
                return JsonRpcResponse(
                    id=request.id,
                    result=self.call_tool(name, arguments),
                )

            return JsonRpcResponse(
                id=request.id,
                error=make_error(-32601, f"Method not found: {request.method}"),
            )
        except KeyError as exc:
            return JsonRpcResponse(id=request.id, error=make_error(-32004, str(exc)))
        except Exception as exc:  # noqa: BLE001
            return JsonRpcResponse(
                id=request.id,
                error=make_error(-32000, "Internal server error", data=str(exc)),
            )
