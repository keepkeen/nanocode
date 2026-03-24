from __future__ import annotations

import json

from multi_provider_tooluse_demo.adapters.anthropic_messages import AnthropicMessagesAdapter
from multi_provider_tooluse_demo.adapters.openai_chat import DeepSeekAdapter, GLMAdapter, KimiAdapter, MiniMaxOpenAIAdapter
from multi_provider_tooluse_demo.adapters.openai_responses import OpenAIResponsesAdapter
from multi_provider_tooluse_demo.models import ToolExecutionResult
from multi_provider_tooluse_demo.tools import GetWeatherTool


def assert_equal(left, right, message: str) -> None:
    if left != right:
        raise AssertionError(f"{message}\nleft={left!r}\nright={right!r}")


def main() -> None:
    weather_tool = GetWeatherTool().spec

    # 1. OpenAI Responses tool shape.
    openai = OpenAIResponsesAdapter(model="gpt-5.4")
    openai_tool = openai.serialize_tool(weather_tool)
    assert_equal(openai_tool["type"], "function", "OpenAI Responses type mismatch")
    assert_equal(openai_tool["name"], "get_weather", "OpenAI Responses tool name mismatch")
    assert "function" not in openai_tool

    # 2. OpenAI-compatible chat shape.
    deepseek = DeepSeekAdapter(model="deepseek-chat")
    deepseek_tool = deepseek.serialize_tool(weather_tool)
    assert_equal(deepseek_tool["type"], "function", "DeepSeek tool type mismatch")
    assert_equal(deepseek_tool["function"]["name"], "get_weather", "DeepSeek function name mismatch")
    assert_equal(deepseek_tool["function"]["strict"], True, "DeepSeek strict missing")

    glm = GLMAdapter(model="glm-5")
    glm_tool = glm.serialize_tool(weather_tool)
    assert "strict" not in glm_tool["function"]

    minimax = MiniMaxOpenAIAdapter(model="MiniMax-M2.7")
    minimax_req = minimax.build_request(minimax.start_state("hello", [weather_tool]))
    assert_equal(minimax_req["reasoning_split"], True, "MiniMax reasoning_split missing")

    kimi = KimiAdapter(model="kimi-k2.5")
    kimi_state = kimi.start_state("hello", [weather_tool])
    kimi_reply = kimi.parse_response(
        {
            "id": "cmpl_x",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "search:0",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": json.dumps({"location": "Hangzhou"}),
                                },
                            }
                        ],
                    },
                }
            ],
        }
    )
    kimi.apply_tool_results(
        kimi_state,
        kimi_reply,
        [ToolExecutionResult(call_id="search:0", name="get_weather", output={"temperature_c": 24})],
    )
    assert_equal(kimi_state.extra["messages"][-1]["name"], "get_weather", "Kimi tool message should include name")

    # 3. Anthropic tool shape and follow-up block shape.
    claude = AnthropicMessagesAdapter(model="claude-sonnet-4.6")
    claude_tool = claude.serialize_tool(weather_tool)
    assert_equal(claude_tool["name"], "get_weather", "Claude tool name mismatch")
    assert_equal(claude_tool["input_schema"]["type"], "object", "Claude input_schema mismatch")

    claude_state = claude.start_state("hello", [weather_tool])
    claude_reply = claude.parse_response(
        {
            "id": "msg_123",
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "get_weather",
                    "input": {"location": "Hangzhou"},
                }
            ],
        }
    )
    claude.apply_tool_results(
        claude_state,
        claude_reply,
        [ToolExecutionResult(call_id="toolu_123", name="get_weather", output={"temperature_c": 24})],
    )
    assert_equal(claude_state.extra["messages"][-1]["role"], "user", "Claude tool result must be user role")
    assert_equal(
        claude_state.extra["messages"][-1]["content"][0]["type"],
        "tool_result",
        "Claude tool result block type mismatch",
    )

    # 4. OpenAI Responses function_call_output follow-up.
    openai_state = openai.start_state("hello", [weather_tool])
    openai_reply = openai.parse_response(
        {
            "id": "resp_123",
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "name": "get_weather",
                    "call_id": "call_123",
                    "arguments": json.dumps({"location": "Hangzhou"}),
                }
            ],
        }
    )
    openai.apply_tool_results(
        openai_state,
        openai_reply,
        [ToolExecutionResult(call_id="call_123", name="get_weather", output={"temperature_c": 24})],
    )
    assert_equal(openai_state.extra["input"][0]["type"], "function_call_output", "OpenAI function_call_output mismatch")
    assert_equal(openai_state.extra["previous_response_id"], "resp_123", "OpenAI previous_response_id mismatch")

    print("All self-tests passed.")


if __name__ == "__main__":
    main()
