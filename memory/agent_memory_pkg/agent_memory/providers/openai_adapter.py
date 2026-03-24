from __future__ import annotations

from typing import Dict, List, Optional

from ..base import BaseProviderAdapter
from ..models import CachePlan, ProviderRequest, ProviderType, ToolSchema


class OpenAIAdapter(BaseProviderAdapter):
    def __init__(self, *, api_style: str = "responses") -> None:
        if api_style not in {"responses", "chat.completions"}:
            raise ValueError("api_style must be 'responses' or 'chat.completions'")
        self.api_style = api_style

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
        if self.api_style == "responses":
            payload: Dict[str, object] = {
                "model": model,
                "input": [m.to_openai_dict() for m in messages],
                "store": extra.get("store", False),
                "prompt_cache_key": cache_plan.provider_hints.get("prompt_cache_key"),
                "prompt_cache_retention": cache_plan.provider_hints.get("prompt_cache_retention", "24h"),
            }
            if extra.get("conversation"):
                payload["conversation"] = extra["conversation"]
            if extra.get("previous_response_id"):
                payload["previous_response_id"] = extra["previous_response_id"]
            if extra.get("enable_compaction", True):
                payload["context_management"] = [
                    {
                        "type": "compaction",
                        "compact_threshold": int(extra.get("compact_threshold", 120000)),
                    }
                ]
            if tools:
                payload["tools"] = [
                    {
                        "type": "function",
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters_json_schema,
                    }
                    for t in tools
                ]
            endpoint_style = "responses"
        else:
            payload = {
                "model": model,
                "messages": [m.to_openai_dict() for m in messages],
                "prompt_cache_key": cache_plan.provider_hints.get("prompt_cache_key"),
                "prompt_cache_retention": cache_plan.provider_hints.get("prompt_cache_retention", "24h"),
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
            endpoint_style = "chat.completions"

        return ProviderRequest(
            provider=ProviderType.OPENAI,
            endpoint_style=endpoint_style,
            payload=payload,
            diagnostics={
                "stable_prefix_fingerprint": cache_plan.diagnostics.get("prefix_fingerprint"),
                "cache_namespace": cache_plan.provider_hints.get("cache_namespace"),
            },
        )
