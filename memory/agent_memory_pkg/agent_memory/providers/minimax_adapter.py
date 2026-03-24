from __future__ import annotations

from typing import Dict, List, Optional

from ..base import BaseProviderAdapter
from ..models import CachePlan, MessageRole, ProviderRequest, ProviderType, ToolSchema


class MiniMaxAdapter(BaseProviderAdapter):
    def __init__(self, *, anthropic_compatible: bool = False) -> None:
        self.anthropic_compatible = anthropic_compatible

    def build_request(
        self,
        *,
        model: str,
        cache_plan: CachePlan,
        tools: Optional[List[ToolSchema]] = None,
        extra: Optional[Dict[str, object]] = None,
    ) -> ProviderRequest:
        extra = extra or {}
        messages = cache_plan.merged_messages()
        if self.anthropic_compatible:
            system_lines = [m.content for m in messages if m.role in {MessageRole.SYSTEM, MessageRole.DEVELOPER}]
            conversation = [m for m in messages if m.role not in {MessageRole.SYSTEM, MessageRole.DEVELOPER}]
            payload: Dict[str, object] = {
                "model": model,
                "system": "\n\n".join(system_lines),
                "messages": [self._to_anthropic_message(m) for m in conversation],
            }
            if conversation:
                payload["messages"][0]["content"][0]["cache_control"] = {"type": "ephemeral"}
            if tools:
                payload["tools"] = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.parameters_json_schema,
                    }
                    for t in tools
                ]
            endpoint_style = "anthropic-compatible"
        else:
            payload = {
                "model": model,
                "messages": [m.to_openai_dict() for m in messages],
            }
            if tools:
                payload["tools"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters_json_schema,
                        },
                    }
                    for t in tools
                ]
            endpoint_style = "native"
        return ProviderRequest(
            provider=ProviderType.MINIMAX,
            endpoint_style=endpoint_style,
            payload=payload,
            diagnostics={
                "cache_mode": "automatic_passive_cache" if not self.anthropic_compatible else "explicit_cache_control",
                "prefix_fingerprint": cache_plan.diagnostics.get("prefix_fingerprint"),
                "notes": "Native API is OpenAI-like; Anthropic-compatible API can place cache_control breakpoints.",
            },
        )

    def _to_anthropic_message(self, message):
        role = "assistant" if message.role == MessageRole.ASSISTANT else "user"
        return {"role": role, "content": [{"type": "text", "text": message.content}]}
