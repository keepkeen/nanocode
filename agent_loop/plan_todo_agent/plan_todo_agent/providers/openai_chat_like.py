from __future__ import annotations

from typing import Any, Dict, List, Optional

from plan_todo_agent.core.interfaces import BaseProviderAdapter
from plan_todo_agent.core.schemas import AgentTurn, ToolSpec


class OpenAIChatLikeAdapter(BaseProviderAdapter):
    name = "openai-chat-like"

    def __init__(
        self,
        *,
        model: str,
        thinking: Optional[Dict[str, Any]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.model = model
        self.thinking = thinking or {}
        self.extra_body = extra_body or {}
        self.base_url = base_url

    def build_request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: List[ToolSpec],
        turn: Optional[AgentTurn] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "tools": [tool.to_openai_chat_tool() for tool in tools],
        }
        if self.thinking:
            payload["thinking"] = self.thinking
        if self.extra_body:
            payload["extra_body"] = self.extra_body
        if self.base_url:
            payload["_meta"] = {"base_url": self.base_url}
        return payload

    def parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        choice = ((response.get("choices") or [{}])[0]).get("message", {})
        return {
            "content": choice.get("content"),
            "reasoning_content": choice.get("reasoning_content"),
            "tool_calls": choice.get("tool_calls") or [],
            "raw_message": choice,
        }

    def format_capabilities(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "api_style": "chat.completions",
            "reasoning": "provider-specific thinking or reasoning_content",
            "tool_use": "OpenAI-style function calling",
        }


class DeepSeekAdapter(OpenAIChatLikeAdapter):
    name = "deepseek"

    def __init__(self, *, model: str = "deepseek-chat", use_thinking_mode: bool = True) -> None:
        if use_thinking_mode:
            super().__init__(
                model=model,
                thinking={"type": "enabled"},
                base_url="https://api.deepseek.com",
            )
        else:
            super().__init__(model=model, base_url="https://api.deepseek.com")


class GLMAdapter(OpenAIChatLikeAdapter):
    name = "glm"

    def __init__(self, *, model: str = "glm-5", use_thinking_mode: bool = True) -> None:
        thinking = {"type": "enabled"} if use_thinking_mode else {"type": "disabled"}
        super().__init__(model=model, thinking=thinking, base_url="https://open.bigmodel.cn/api/paas/v4")


class KimiAdapter(OpenAIChatLikeAdapter):
    name = "kimi"

    def __init__(self, *, model: str = "kimi-k2-0905-preview", use_thinking_mode: bool = False) -> None:
        if use_thinking_mode:
            model = "kimi-thinking-preview" if model == "kimi-k2-0905-preview" else model
        super().__init__(model=model, base_url="https://api.moonshot.cn/v1")
