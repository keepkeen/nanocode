from __future__ import annotations

from typing import Dict, List, Optional

from ..base import BaseProviderAdapter
from ..models import ContextAssembly, Message, MessageRole, ProviderRequest, ProviderType, ToolSchema


def _tool_payload_openai_style(tools: List[ToolSchema]) -> List[Dict[str, object]]:
    return [
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


class DeepSeekAdapter(BaseProviderAdapter):
    def build_request(self, *, model: str, assembly: ContextAssembly, tools: Optional[List[ToolSchema]] = None, extra: Optional[Dict[str, object]] = None) -> ProviderRequest:
        payload: Dict[str, object] = {"model": model, "messages": [m.to_openai_dict() for m in assembly.merged_messages()]}
        if tools:
            payload["tools"] = _tool_payload_openai_style(tools)
        return ProviderRequest(
            provider=ProviderType.DEEPSEEK,
            endpoint_style="chat.completions",
            path="/chat/completions",
            payload=payload,
            diagnostics={
                "cache_mode": "implicit_prefix_cache",
                "tracked_fields": ["usage.prompt_cache_hit_tokens", "usage.prompt_cache_miss_tokens"],
            },
        )


class GLMAdapter(BaseProviderAdapter):
    def build_request(self, *, model: str, assembly: ContextAssembly, tools: Optional[List[ToolSchema]] = None, extra: Optional[Dict[str, object]] = None) -> ProviderRequest:
        extra = extra or {}
        payload: Dict[str, object] = {"model": model, "messages": [m.to_openai_dict() for m in assembly.merged_messages()]}
        if extra.get("thinking_type"):
            payload["thinking"] = {"type": str(extra["thinking_type"])}
        if tools:
            payload["tools"] = _tool_payload_openai_style(tools)
        return ProviderRequest(
            provider=ProviderType.GLM,
            endpoint_style="chat.completions",
            path="/api/paas/v4/chat/completions",
            payload=payload,
            diagnostics={
                "cache_mode": "implicit_context_cache",
                "tracked_fields": ["usage.prompt_tokens_details.cached_tokens"],
            },
        )


class KimiAdapter(BaseProviderAdapter):
    def build_request(self, *, model: str, assembly: ContextAssembly, tools: Optional[List[ToolSchema]] = None, extra: Optional[Dict[str, object]] = None) -> ProviderRequest:
        extra = extra or {}
        messages = []
        if extra.get("cache_id"):
            cache_content = f"cache_id={extra['cache_id']}"
            if extra.get("reset_ttl"):
                cache_content += f";reset_ttl={int(extra['reset_ttl'])}"
            messages.append({"role": "cache", "content": cache_content})
        messages.extend(m.to_openai_dict() for m in assembly.merged_messages())
        payload: Dict[str, object] = {"model": model, "messages": messages}
        if extra.get("thinking_type"):
            payload["thinking"] = {"type": str(extra["thinking_type"])}
        if tools:
            payload["tools"] = _tool_payload_openai_style(tools)
        return ProviderRequest(
            provider=ProviderType.KIMI,
            endpoint_style="chat.completions",
            path="/chat/completions",
            payload=payload,
            diagnostics={
                "cache_mode": "explicit_context_cache_reference",
                "cache_reference_role": "cache",
            },
        )

    @staticmethod
    def build_create_cache_request(*, model: str, messages: List[Dict[str, object]], tools: Optional[List[ToolSchema]] = None, name: str = "shared-prefix", ttl: int = 3600) -> ProviderRequest:
        payload: Dict[str, object] = {"model": model, "messages": messages, "name": name, "ttl": ttl}
        if tools:
            payload["tools"] = _tool_payload_openai_style(tools)
        return ProviderRequest(
            provider=ProviderType.KIMI,
            endpoint_style="context_cache_create",
            path="/v1/caching",
            payload=payload,
        )


class MiniMaxAdapter(BaseProviderAdapter):
    def __init__(self, *, anthropic_compatible: bool = False) -> None:
        self.anthropic_compatible = anthropic_compatible

    def build_request(self, *, model: str, assembly: ContextAssembly, tools: Optional[List[ToolSchema]] = None, extra: Optional[Dict[str, object]] = None) -> ProviderRequest:
        messages = assembly.merged_messages()
        if self.anthropic_compatible:
            system_text = "\n\n".join(m.content for m in messages if m.role in {MessageRole.SYSTEM, MessageRole.DEVELOPER})
            convo = []
            for msg in messages:
                if msg.role in {MessageRole.SYSTEM, MessageRole.DEVELOPER}:
                    continue
                role = "assistant" if msg.role == MessageRole.ASSISTANT else "user"
                convo.append({"role": role, "content": [{"type": "text", "text": msg.content}]})
            payload: Dict[str, object] = {"model": model, "system": system_text, "messages": convo, "cache_control": {"type": "ephemeral"}}
            if tools:
                payload["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters_json_schema} for t in tools]
            return ProviderRequest(provider=ProviderType.MINIMAX, endpoint_style="anthropic-compatible", path="/v1/messages", payload=payload)

        payload_messages = []
        for msg in messages:
            provider_role = msg.metadata.get("minimax_role") or msg.role.value
            payload = {"role": provider_role, "content": msg.content}
            if msg.name:
                payload["name"] = msg.name
            payload_messages.append(payload)
        payload = {"model": model, "messages": payload_messages}
        if tools:
            payload["tools"] = _tool_payload_openai_style(tools)
        return ProviderRequest(
            provider=ProviderType.MINIMAX,
            endpoint_style="chat.completions",
            path="/chat/completions",
            payload=payload,
            diagnostics={"cache_mode": "automatic_passive_cache"},
        )
