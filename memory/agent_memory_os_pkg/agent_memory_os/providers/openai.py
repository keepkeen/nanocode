from __future__ import annotations

from typing import Dict, List, Optional

from ..base import BaseProviderAdapter
from ..models import ContextAssembly, ProviderRequest, ProviderType, ToolSchema


class OpenAIResponsesAdapter(BaseProviderAdapter):
    def build_request(
        self,
        *,
        model: str,
        assembly: ContextAssembly,
        tools: Optional[List[ToolSchema]] = None,
        extra: Optional[Dict[str, object]] = None,
    ) -> ProviderRequest:
        extra = extra or {}
        payload: Dict[str, object] = {
            "model": model,
            "input": [m.to_openai_dict() for m in assembly.merged_messages()],
            "store": bool(extra.get("store", False)),
        }
        if extra.get("prompt_cache_key") or assembly.provider_hints.get("stable_prefix_hash"):
            payload["prompt_cache_key"] = str(extra.get("prompt_cache_key") or assembly.provider_hints["stable_prefix_hash"])
        if extra.get("prompt_cache_retention"):
            payload["prompt_cache_retention"] = extra["prompt_cache_retention"]
        if extra.get("previous_response_id"):
            payload["previous_response_id"] = extra["previous_response_id"]
        if extra.get("conversation"):
            payload["conversation"] = extra["conversation"]
        if extra.get("enable_compaction", True):
            payload["context_management"] = [
                {
                    "type": "compaction",
                    "compact_threshold": int(extra.get("compact_threshold", 150000)),
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
        native_mcp_tools = list(extra.get("native_mcp_tools", []))
        if native_mcp_tools:
            payload.setdefault("tools", [])
            payload["tools"].extend(native_mcp_tools)
        return ProviderRequest(
            provider=ProviderType.OPENAI,
            endpoint_style="responses",
            path="/responses",
            payload=payload,
            diagnostics={
                "stable_prefix_hash": assembly.provider_hints.get("stable_prefix_hash"),
                "warning": "Set prompt_cache_retention='24h' only on models that support extended retention.",
            },
        )


class OpenAIChatAdapter(BaseProviderAdapter):
    def build_request(
        self,
        *,
        model: str,
        assembly: ContextAssembly,
        tools: Optional[List[ToolSchema]] = None,
        extra: Optional[Dict[str, object]] = None,
    ) -> ProviderRequest:
        extra = extra or {}
        payload: Dict[str, object] = {
            "model": model,
            "messages": [m.to_openai_dict() for m in assembly.merged_messages()],
        }
        if extra.get("prompt_cache_key") or assembly.provider_hints.get("stable_prefix_hash"):
            payload["prompt_cache_key"] = str(extra.get("prompt_cache_key") or assembly.provider_hints["stable_prefix_hash"])
        if extra.get("prompt_cache_retention"):
            payload["prompt_cache_retention"] = extra["prompt_cache_retention"]
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
        native_mcp_tools = list(extra.get("native_mcp_tools", []))
        if native_mcp_tools:
            payload.setdefault("tools", [])
            payload["tools"].extend(native_mcp_tools)
        return ProviderRequest(
            provider=ProviderType.OPENAI,
            endpoint_style="chat.completions",
            path="/chat/completions",
            payload=payload,
            diagnostics={"stable_prefix_hash": assembly.provider_hints.get("stable_prefix_hash")},
        )
