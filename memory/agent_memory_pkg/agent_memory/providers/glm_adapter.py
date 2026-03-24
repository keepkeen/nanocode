from __future__ import annotations

from typing import Dict, List, Optional

from ..base import BaseProviderAdapter
from ..models import CachePlan, ProviderRequest, ProviderType, ToolSchema


class GLMAdapter(BaseProviderAdapter):
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
        return ProviderRequest(
            provider=ProviderType.GLM,
            endpoint_style="chat.completions",
            payload=payload,
            diagnostics={
                "cache_mode": "implicit_context_cache",
                "tracked_usage_field": "usage.prompt_tokens_details.cached_tokens",
                "prefix_fingerprint": cache_plan.diagnostics.get("prefix_fingerprint"),
            },
        )
