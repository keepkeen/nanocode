from __future__ import annotations

import os
from typing import Callable

from multi_provider_tooluse_demo.agent import ToolUseAgent
from multi_provider_tooluse_demo.providers import (
    make_claude_provider,
    make_deepseek_provider,
    make_glm_provider,
    make_kimi_provider,
    make_minimax_provider,
    make_openai_provider,
)
from multi_provider_tooluse_demo.tools import GetWeatherTool, ToolRegistry
from multi_provider_tooluse_demo.transports import RequestsTransport


def run_demo(label: str, provider_factory: Callable[[], object], api_key_env: str) -> None:
    api_key = os.getenv(api_key_env)
    if not api_key:
        print(f"[skip] {label}: missing {api_key_env}")
        return

    registry = ToolRegistry([GetWeatherTool()])
    agent = ToolUseAgent(
        provider=provider_factory(),
        transport=RequestsTransport(),
        api_key=api_key,
        registry=registry,
    )
    result = agent.run("What is the weather in Hangzhou?")
    print(f"\n=== {label} ===")
    print(result.final_response.text)


if __name__ == "__main__":
    run_demo("OpenAI Responses", lambda: make_openai_provider("gpt-5.4"), "OPENAI_API_KEY")
    run_demo("DeepSeek", lambda: make_deepseek_provider("deepseek-chat"), "DEEPSEEK_API_KEY")
    run_demo("GLM", lambda: make_glm_provider("glm-5"), "ZAI_API_KEY")
    run_demo("MiniMax", lambda: make_minimax_provider("MiniMax-M2.7"), "MINIMAX_API_KEY")
    run_demo("Kimi", lambda: make_kimi_provider("kimi-k2.5"), "MOONSHOT_API_KEY")
    run_demo("Claude", lambda: make_claude_provider("claude-sonnet-4.6"), "ANTHROPIC_API_KEY")
