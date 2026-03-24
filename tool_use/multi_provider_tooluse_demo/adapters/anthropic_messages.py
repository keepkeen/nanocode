from __future__ import annotations

from typing import Any, Dict, List

from ..models import JSONDict, NormalizedResponse, ToolCall, ToolExecutionResult, ToolSpec
from .base import ConversationState, ProviderAdapter


class AnthropicMessagesAdapter(ProviderAdapter):
    provider_name = "anthropic-messages"

    def __init__(self, model: str, base_url: str = "https://api.anthropic.com"):
        super().__init__(model=model)
        self._base_url = base_url

    def base_url(self) -> str:
        return self._base_url

    def path(self) -> str:
        return "/v1/messages"

    def headers(self, api_key: str) -> Dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def serialize_tool(self, tool: ToolSpec) -> JSONDict:
        payload: JSONDict = {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }
        if tool.strict:
            payload["strict"] = True
        return payload

    def start_state(self, user_prompt: str, tools: List[ToolSpec]) -> ConversationState:
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_prompt}],
            }
        ]
        return ConversationState(request_tools=self.serialize_tools(tools), extra={"messages": messages})

    def build_request(self, state: ConversationState) -> JSONDict:
        return {
            "model": self.model,
            "max_tokens": 1024,
            "tools": state.request_tools,
            "messages": state.extra["messages"],
        }

    def parse_response(self, data: JSONDict) -> NormalizedResponse:
        content_blocks = data.get("content", [])
        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []
        for block in content_blocks:
            block_type = block.get("type")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        call_id=block["id"],
                        name=block["name"],
                        arguments_json=__import__("json").dumps(block.get("input", {}), ensure_ascii=False),
                        arguments=block.get("input", {}),
                    )
                )
        return NormalizedResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason"),
            raw_assistant_message={"role": "assistant", "content": content_blocks},
            raw_response=data,
            response_id=data.get("id"),
        )

    def apply_tool_results(
        self,
        state: ConversationState,
        response: NormalizedResponse,
        tool_results: List[ToolExecutionResult],
    ) -> None:
        state.extra["messages"].append(response.raw_assistant_message)
        result_blocks = []
        for tool_result in tool_results:
            result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_result.call_id,
                    "is_error": tool_result.is_error,
                    "content": tool_result.as_text(),
                }
            )
        state.extra["messages"].append({"role": "user", "content": result_blocks})
