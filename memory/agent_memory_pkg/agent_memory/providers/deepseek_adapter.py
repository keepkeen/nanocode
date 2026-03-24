from __future__ import annotations

from typing import Dict, List, Optional

from ..base import BaseProviderAdapter
from ..models import CachePlan, ProviderRequest, ProviderType, ToolSchema


class DeepSeekAdapter(BaseProviderAdapter):
    def build_request(
        self,
        *,
        model: str,
        cache_plan: CachePlan,
        tools: Optional[List[ToolSchema]] = None,
        extra: Optional[Dict[str, object]] = None,
    ) -> ProviderRequest:
        payload: Dict[str, object] = {
            "model": model,
            "messages": [m.to_openai_dict() for m in cache_plan.merged_messages()],
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
        return ProviderRequest(
            provider=ProviderType.DEEPSEEK,
            endpoint_style="chat.completions",
            payload=payload,
            diagnostics={
                "cache_mode": "implicit_prefix_disk_cache",
                "prefix_fingerprint": cache_plan.diagnostics.get("prefix_fingerprint"),
                "notes": "Keep the stable prefix byte-identical to maximize prompt_cache_hit_tokens.",
            },
        )
