from __future__ import annotations

import json
from typing import Any, Dict, List

from ..models import JSONDict, NormalizedResponse, ToolCall, ToolExecutionResult, ToolSpec
from .base import ConversationState, ProviderAdapter


class OpenAIChatCompatibleAdapter(ProviderAdapter):
    provider_name = "openai-chat-compatible"
    api_base_url = ""
    api_path = "/chat/completions"
    system_prompt = None
    add_tool_message_name = False
    default_tool_choice = "auto"

    def base_url(self) -> str:
        return self.api_base_url

    def path(self) -> str:
        return self.api_path

    def headers(self, api_key: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def serialize_tool(self, tool: ToolSpec) -> JSONDict:
        function: JSONDict = {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
        if self._supports_tool_strict():
            function["strict"] = tool.strict
        return {"type": "function", "function": function}

    def _supports_tool_strict(self) -> bool:
        return False

    def start_state(self, user_prompt: str, tools: List[ToolSpec]) -> ConversationState:
        messages: List[JSONDict] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return ConversationState(
            request_tools=self.serialize_tools(tools),
            extra={"messages": messages},
        )

    def build_request(self, state: ConversationState) -> JSONDict:
        body: JSONDict = {
            "model": self.model,
            "messages": state.extra["messages"],
            "tools": state.request_tools,
        }
        if self.default_tool_choice is not None:
            body["tool_choice"] = self.default_tool_choice
        extra_body = self.extra_body()
        if extra_body:
            body.update(extra_body)
        return body

    def extra_body(self) -> JSONDict:
        return {}

    def parse_response(self, data: JSONDict) -> NormalizedResponse:
        choice = data["choices"][0]
        message = choice["message"]
        tool_calls = []
        for item in message.get("tool_calls") or []:
            arguments_json = item["function"]["arguments"]
            tool_calls.append(
                ToolCall(
                    call_id=item["id"],
                    name=item["function"]["name"],
                    arguments_json=arguments_json,
                    arguments=json.loads(arguments_json),
                )
            )
        return NormalizedResponse(
            text=message.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason"),
            raw_assistant_message=message,
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
        for tool_result in tool_results:
            tool_message: JSONDict = {
                "role": "tool",
                "tool_call_id": tool_result.call_id,
                "content": tool_result.as_text(),
            }
            if self.add_tool_message_name:
                tool_message["name"] = tool_result.name
            state.extra["messages"].append(tool_message)


class DeepSeekAdapter(OpenAIChatCompatibleAdapter):
    provider_name = "deepseek"
    api_base_url = "https://api.deepseek.com"

    def _supports_tool_strict(self) -> bool:
        return True


class GLMAdapter(OpenAIChatCompatibleAdapter):
    provider_name = "glm"
    api_base_url = "https://open.bigmodel.cn/api/paas/v4"
    default_tool_choice = "auto"


class MiniMaxOpenAIAdapter(OpenAIChatCompatibleAdapter):
    provider_name = "minimax-openai-compatible"
    api_base_url = "https://api.minimaxi.com/v1"

    def extra_body(self) -> JSONDict:
        # MiniMax recommends preserving reasoning details in multi-step tool use.
        return {"reasoning_split": True}


class KimiAdapter(OpenAIChatCompatibleAdapter):
    provider_name = "kimi"
    api_base_url = "https://api.moonshot.cn/v1"
    add_tool_message_name = True
