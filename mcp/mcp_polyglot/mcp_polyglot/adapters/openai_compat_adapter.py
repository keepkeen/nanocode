from __future__ import annotations

from typing import Iterable, Optional

from .base import BaseProviderAdapter, NativeMcpEndpoint
from ..core.server import BaseMcpServer
from ..core.tool import BaseMcpTool


class OpenAICompatibleFunctionAdapter(BaseProviderAdapter):
    """
    适用于公开 API 以 OpenAI-compatible function calling 为主的厂商。
    """

    supports_native_remote_mcp = False
    supports_openai_compatible_function_calling = True
    base_url: Optional[str] = None

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
            raise ValueError(
                f"{self.provider_name} public adapter does not expose native remote MCP "
                "in this example; convert MCP tools into function-calling tools instead."
            )

        concrete_tools = list(tools or [])
        if server is not None and not concrete_tools:
            concrete_tools = list(server._tools.values())  # noqa: SLF001

        if not concrete_tools:
            raise ValueError(f"{self.provider_name} adapter requires tools or server.")

        return {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [tool.to_openai_compatible_function() for tool in concrete_tools],
            "tool_choice": "auto",
        }
