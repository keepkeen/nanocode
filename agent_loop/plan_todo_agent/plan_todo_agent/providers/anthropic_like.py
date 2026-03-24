from __future__ import annotations

from typing import Any, Dict, List, Optional

from plan_todo_agent.core.interfaces import BaseProviderAdapter
from plan_todo_agent.core.schemas import AgentTurn, ToolSpec


class AnthropicMessagesAdapter(BaseProviderAdapter):
    name = "anthropic-messages"

    def __init__(
        self,
        *,
        model: str,
        max_tokens: int = 4096,
        thinking: Optional[Dict[str, Any]] = None,
        beta_headers: Optional[List[str]] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.thinking = thinking or {}
        self.beta_headers = beta_headers or []
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
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_prompt}],
                }
            ],
            "tools": [tool.to_anthropic_tool() for tool in tools],
            "tool_choice": {"type": "auto"},
        }
        if self.thinking:
            payload["thinking"] = self.thinking
        if self.beta_headers:
            payload["_meta"] = {
                "anthropic-beta": list(self.beta_headers),
                "base_url": self.base_url,
            }
        elif self.base_url:
            payload["_meta"] = {"base_url": self.base_url}
        return payload

    def parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        content = response.get("content") or []
        blocks: Dict[str, Any] = {"thinking": [], "text": [], "tool_use": []}
        for block in content:
            block_type = block.get("type")
            if block_type == "thinking":
                blocks["thinking"].append(block)
            elif block_type == "text":
                blocks["text"].append(block)
            elif block_type == "tool_use":
                blocks["tool_use"].append(block)
        return blocks

    def format_capabilities(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "api_style": "anthropic.messages",
            "reasoning": "thinking content blocks",
            "tool_use": "client tools with input_schema",
        }


class AnthropicAdapter(AnthropicMessagesAdapter):
    name = "anthropic"

    def __init__(self, *, model: str = "claude-sonnet-4-20250514", interleaved: bool = True) -> None:
        beta_headers = ["interleaved-thinking-2025-05-14"] if interleaved else []
        super().__init__(
            model=model,
            thinking={"type": "enabled", "budget_tokens": 2048},
            beta_headers=beta_headers,
            base_url="https://api.anthropic.com/v1",
        )


class MiniMaxAdapter(AnthropicMessagesAdapter):
    name = "minimax"

    def __init__(self, *, model: str = "MiniMax-M2.5") -> None:
        super().__init__(
            model=model,
            thinking={"type": "enabled", "budget_tokens": 2048},
            base_url="https://api.minimax.io/anthropic",
        )
