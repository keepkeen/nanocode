from __future__ import annotations

import json

from ..adapters.anthropic_adapter import AnthropicMcpAdapter
from ..adapters.base import NativeMcpEndpoint
from ..adapters.deepseek_adapter import DeepSeekAdapter
from ..adapters.glm_adapter import GLMAdapter
from ..adapters.kimi_adapter import KimiAdapter
from ..adapters.minimax_adapter import MiniMaxFunctionAdapter
from ..adapters.openai_adapter import OpenAIResponsesMcpAdapter
from .weather_tool import WeatherMcpServer


def show(name: str, payload: dict) -> None:
    print("=" * 80)
    print(name)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()


def main() -> None:
    server = WeatherMcpServer()
    prompt = "杭州现在天气怎么样？"

    native_endpoint = NativeMcpEndpoint(
        server_label="weather_mcp",
        server_url="http://127.0.0.1:8000/mcp",
        server_description="A demo weather MCP server.",
        authorization="Bearer YOUR_TOKEN_IF_NEEDED",
    )

    openai_payload = OpenAIResponsesMcpAdapter().build_payload(
        prompt=prompt,
        model="gpt-5",
        native_mcp=native_endpoint,
    )
    show("OpenAI Responses API / native MCP", openai_payload)

    anthropic_payload = AnthropicMcpAdapter().build_payload(
        prompt=prompt,
        model="claude-opus-4-6",
        native_mcp=native_endpoint,
    )
    show("Anthropic Messages API / native MCP", anthropic_payload)

    deepseek_payload = DeepSeekAdapter().build_payload(
        prompt=prompt,
        model="deepseek-chat",
        server=server,
    )
    show("DeepSeek / Tool Calls", deepseek_payload)

    glm_payload = GLMAdapter().build_payload(
        prompt=prompt,
        model="glm-5",
        server=server,
    )
    show("GLM / Function Calling", glm_payload)

    minimax_payload = MiniMaxFunctionAdapter().build_payload(
        prompt=prompt,
        model="MiniMax-M1-40k",
        server=server,
    )
    show("MiniMax / Function Calling", minimax_payload)

    kimi_payload = KimiAdapter().build_payload(
        prompt=prompt,
        model="kimi-k2.5",
        server=server,
    )
    show("Kimi / Tool Use", kimi_payload)

    kimi_builtin_web_search = KimiAdapter().build_builtin_web_search_payload(
        prompt="请搜索今天 OpenAI MCP 文档更新了什么？",
        model="kimi-k2.5",
    )
    show("Kimi / builtin_function.$web_search", kimi_builtin_web_search)


if __name__ == "__main__":
    main()
