from __future__ import annotations

from typing import Iterable, Optional

from .base import BaseProviderAdapter, NativeMcpEndpoint
from ..core.server import BaseMcpServer
from ..core.tool import BaseMcpTool


class OpenAIResponsesMcpAdapter(BaseProviderAdapter):
    provider_name = "openai"
    supports_native_remote_mcp = True
    supports_openai_compatible_function_calling = True

    def build_payload(
        self,
        *,
        prompt: str,
        model: str,
        server: Optional[BaseMcpServer] = None,
        tools: Optional[Iterable[BaseMcpTool]] = None,
        native_mcp: Optional[NativeMcpEndpoint] = None,
    ) -> dict:
        if native_mcp is not None:
            mcp_tool: dict = {
                "type": "mcp",
                "server_label": native_mcp.server_label,
                "server_url": native_mcp.server_url,
                "require_approval": "never",
            }
            if native_mcp.server_description:
                mcp_tool["server_description"] = native_mcp.server_description
            if native_mcp.authorization:
                mcp_tool["authorization"] = native_mcp.authorization
            if native_mcp.connector_id:
                mcp_tool["connector_id"] = native_mcp.connector_id

            return {
                "model": model,
                "input": prompt,
                "tools": [mcp_tool],
            }

        concrete_tools = list(tools or [])
        if server is not None and not concrete_tools:
            concrete_tools = list(server._tools.values())  # noqa: SLF001

        if not concrete_tools:
            raise ValueError("OpenAI adapter requires either native_mcp or tools/server.")

        return {
            "model": model,
            "input": prompt,
            "tools": [tool.to_openai_compatible_function() for tool in concrete_tools],
        }
