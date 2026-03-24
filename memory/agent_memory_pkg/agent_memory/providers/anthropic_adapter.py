from __future__ import annotations

from typing import Dict, List, Optional

from ..base import BaseProviderAdapter
from ..models import CachePlan, MessageRole, ProviderRequest, ProviderType, ToolSchema


class AnthropicAdapter(BaseProviderAdapter):
    def build_request(
        self,
        *,
        model: str,
        cache_plan: CachePlan,
        tools: Optional[List[ToolSchema]] = None,
        extra: Optional[Dict[str, object]] = None,
    ) -> ProviderRequest:
        extra = extra or {}
        all_messages = cache_plan.merged_messages()
        system_text = "\n\n".join(
            [m.content for m in all_messages if m.role in {MessageRole.SYSTEM, MessageRole.DEVELOPER}]
        )
        user_assistant_messages = [m for m in all_messages if m.role not in {MessageRole.SYSTEM, MessageRole.DEVELOPER}]
        anthropic_messages = [self._to_message_block(m) for m in user_assistant_messages]

        if anthropic_messages and cache_plan.provider_hints.get("cache_control"):
            anthropic_messages[0]["content"][0]["cache_control"] = cache_plan.provider_hints["cache_control"]

        payload: Dict[str, object] = {
            "model": model,
            "system": system_text,
            "messages": anthropic_messages,
            "max_tokens": int(extra.get("max_tokens", 4096)),
        }
        if tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters_json_schema,
                }
                for t in tools
            ]
        if extra.get("enable_compaction", True):
            payload["context_management"] = {
                "edits": [
                    {
                        "type": "compact_20260112",
                        "trigger": {"tokens": int(extra.get("compact_threshold", 120000))},
                    }
                ]
            }
            if extra.get("compaction_instructions"):
                payload["context_management"]["edits"][0]["instructions"] = extra["compaction_instructions"]
            if extra.get("pause_after_compaction"):
                payload["context_management"]["edits"][0]["pause_after_compaction"] = True

        headers = {"anthropic-beta": "compact-2026-01-12"} if extra.get("enable_compaction", True) else {}
        return ProviderRequest(
            provider=ProviderType.ANTHROPIC,
            endpoint_style="messages",
            payload=payload,
            headers=headers,
            diagnostics={
                "cache_breakpoint": "first user block after stable prefix",
                "prefix_fingerprint": cache_plan.diagnostics.get("prefix_fingerprint"),
            },
        )

    def _to_message_block(self, message):
        role = "assistant" if message.role == MessageRole.ASSISTANT else "user"
        return {"role": role, "content": [{"type": "text", "text": message.content}]}
