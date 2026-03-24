from __future__ import annotations

from typing import Iterable, Optional

from .openai_compat_adapter import OpenAICompatibleFunctionAdapter
from .base import NativeMcpEndpoint
from ..core.server import BaseMcpServer
from ..core.tool import BaseMcpTool


class KimiAdapter(OpenAICompatibleFunctionAdapter):
    provider_name = "kimi"
    base_url = "https://api.moonshot.cn/v1"

    def build_builtin_web_search_payload(self, *, prompt: str, model: str = "kimi-k2.5") -> dict:
        return {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "extra_body": {"thinking": {"type": "disabled"}},
            "tools": [
                {
                    "type": "builtin_function",
                    "function": {"name": "$web_search"},
                }
            ],
        }

    def build_payload(
        self,
        *,
        prompt: str,
        model: str,
        server: Optional[BaseMcpServer] = None,
        tools: Optional[Iterable[BaseMcpTool]] = None,
        native_mcp: Optional[NativeMcpEndpoint] = None,
    ) -> dict:
        return super().build_payload(
            prompt=prompt,
            model=model,
            server=server,
            tools=tools,
            native_mcp=native_mcp,
        )
