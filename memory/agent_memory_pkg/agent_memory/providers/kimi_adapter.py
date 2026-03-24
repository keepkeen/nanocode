from __future__ import annotations

from typing import Dict, List, Optional

from ..base import BaseProviderAdapter
from ..models import CachePlan, ProviderRequest, ProviderType, ToolSchema


class KimiAdapter(BaseProviderAdapter):
    def __init__(self, *, use_context_cache_headers: bool = True) -> None:
        self.use_context_cache_headers = use_context_cache_headers

    def build_request(
        self,
        *,
        model: str,
        cache_plan: CachePlan,
        tools: Optional[List[ToolSchema]] = None,
        extra: Optional[Dict[str, object]] = None,
    ) -> ProviderRequest:
        extra = extra or {}
        payload: Dict[str, object] = {
            "model": model,
            "messages": [m.to_openai_dict() for m in cache_plan.merged_messages()],
        }
        if extra.get("thinking_type"):
            payload["thinking"] = {"type": extra["thinking_type"]}
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
        headers: Dict[str, str] = {}
        if self.use_context_cache_headers:
            headers["X-Msh-Context-Cache"] = str(cache_plan.provider_hints.get("kimi_context_cache_key"))
            headers["X-Msh-Context-Cache-Reset-TTL"] = str(
                cache_plan.provider_hints.get("kimi_context_cache_ttl_seconds", 3600)
            )
        return ProviderRequest(
            provider=ProviderType.KIMI,
            endpoint_style="chat.completions",
            payload=payload,
            headers=headers,
            diagnostics={
                "cache_mode": "explicit_context_cache",
                "cache_namespace": cache_plan.provider_hints.get("cache_namespace"),
                "notes": "Kimi chat is stateless; persist messages client-side or through your own memory layer.",
            },
        )

    @staticmethod
    def build_create_cache_request(*, model: str, reusable_text: str, ttl_seconds: int = 3600) -> Dict[str, object]:
        return {
            "method": "POST",
            "path": "/v1/caching",
            "json": {
                "model": model,
                "messages": [{"role": "user", "content": reusable_text}],
                "ttl": ttl_seconds,
            },
        }
