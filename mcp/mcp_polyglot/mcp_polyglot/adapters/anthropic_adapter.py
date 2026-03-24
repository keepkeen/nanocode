from __future__ import annotations

from typing import Iterable, Optional

from .base import BaseProviderAdapter, NativeMcpEndpoint
from ..core.server import BaseMcpServer
from ..core.tool import BaseMcpTool


class AnthropicMcpAdapter(BaseProviderAdapter):
    provider_name = "anthropic"
    supports_native_remote_mcp = True
    supports_openai_compatible_function_calling = False
    beta_header = "mcp-client-2025-11-20"

    def build_payload(
        self,
        *,
        prompt: str,
        model: str,
        server: Optional[BaseMcpServer] = None,
        tools: Optional[Iterable[BaseMcpTool]] = None,
        native_mcp: Optional[NativeMcpEndpoint] = None,
    ) -> dict:
        if native_mcp is None:
            raise ValueError("Anthropic adapter currently expects native_mcp.")

        server_name = native_mcp.server_label
        mcp_server: dict = {
            "type": "url",
            "url": native_mcp.server_url,
            "name": server_name,
        }
        if native_mcp.authorization:
            mcp_server["authorization_token"] = native_mcp.authorization

        return {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
            "mcp_servers": [mcp_server],
            "tools": [
                {
                    "type": "mcp_toolset",
                    "mcp_server_name": server_name,
                }
            ],
            "_meta": {
                "required_headers": {
                    "anthropic-beta": self.beta_header,
                    "anthropic-version": "2023-06-01",
                }
            },
        }
