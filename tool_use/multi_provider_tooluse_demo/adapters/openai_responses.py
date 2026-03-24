from __future__ import annotations

import json
from typing import Any, Dict, List

from ..models import JSONDict, NormalizedResponse, ToolCall, ToolExecutionResult, ToolSpec
from .base import ConversationState, ProviderAdapter


class OpenAIResponsesAdapter(ProviderAdapter):
    provider_name = "openai-responses"

    def base_url(self) -> str:
        return "https://api.openai.com/v1"

    def path(self) -> str:
        return "/responses"

    def headers(self, api_key: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def serialize_tool(self, tool: ToolSpec) -> JSONDict:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "strict": tool.strict,
        }

    def start_state(self, user_prompt: str, tools: List[ToolSpec]) -> ConversationState:
        return ConversationState(
            request_tools=self.serialize_tools(tools),
            extra={
                "input": user_prompt,
                "previous_response_id": None,
            },
        )

    def build_request(self, state: ConversationState) -> JSONDict:
        body: JSONDict = {
            "model": self.model,
            "tools": state.request_tools,
            "input": state.extra["input"],
        }
        if state.extra.get("previous_response_id"):
            body["previous_response_id"] = state.extra["previous_response_id"]
        return body

    def parse_response(self, data: JSONDict) -> NormalizedResponse:
        output = data.get("output", [])
        text_fragments: List[str] = []
        tool_calls: List[ToolCall] = []

        for item in output:
            item_type = item.get("type")
            if item_type == "function_call":
                arguments_json = item["arguments"]
                tool_calls.append(
                    ToolCall(
                        call_id=item["call_id"],
                        name=item["name"],
                        arguments_json=arguments_json,
                        arguments=json.loads(arguments_json),
                    )
                )
            elif item_type == "message":
                for block in item.get("content", []):
                    block_type = block.get("type")
                    if block_type == "output_text":
                        text_fragments.append(block.get("text", ""))
                    elif block_type == "text":
                        text_fragments.append(block.get("text", ""))

        return NormalizedResponse(
            text="".join(text_fragments),
            tool_calls=tool_calls,
            finish_reason=data.get("status"),
            raw_assistant_message=output,
            raw_response=data,
            response_id=data.get("id"),
        )

    def apply_tool_results(
        self,
        state: ConversationState,
        response: NormalizedResponse,
        tool_results: List[ToolExecutionResult],
    ) -> None:
        state.extra["previous_response_id"] = response.response_id
        state.extra["input"] = [
            {
                "type": "function_call_output",
                "call_id": tool_result.call_id,
                "output": tool_result.as_text(),
            }
            for tool_result in tool_results
        ]
