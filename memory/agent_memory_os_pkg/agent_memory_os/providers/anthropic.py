from __future__ import annotations

from typing import Dict, List, Optional

from ..base import BaseProviderAdapter
from ..models import ContextAssembly, MessageRole, ProviderRequest, ProviderType, ToolSchema


class AnthropicMessagesAdapter(BaseProviderAdapter):
    def build_request(
        self,
        *,
        model: str,
        assembly: ContextAssembly,
        tools: Optional[List[ToolSchema]] = None,
        extra: Optional[Dict[str, object]] = None,
    ) -> ProviderRequest:
        extra = extra or {}
        messages = assembly.merged_messages()
        system_blocks = []
        convo = []
        for msg in messages:
            if msg.role in {MessageRole.SYSTEM, MessageRole.DEVELOPER}:
                system_blocks.append({"type": "text", "text": msg.content})
            else:
                role = "assistant" if msg.role == MessageRole.ASSISTANT else "user"
                convo.append({"role": role, "content": [{"type": "text", "text": msg.content}]})

        payload: Dict[str, object] = {
            "model": model,
            "max_tokens": int(extra.get("max_tokens", 4096)),
            "system": system_blocks if len(system_blocks) > 1 else (system_blocks[0]["text"] if system_blocks else ""),
            "messages": convo,
        }
        if extra.get("enable_prompt_caching", True):
            payload["cache_control"] = {"type": "ephemeral"}
            if extra.get("cache_ttl") == "1h":
                payload["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
        if tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters_json_schema,
                }
                for t in tools
            ]
        native_mcp_servers = list(extra.get("anthropic_mcp_servers", []))
        if native_mcp_servers:
            payload["mcp_servers"] = native_mcp_servers
            payload.setdefault("tools", [])
            payload["tools"].extend(
                {
                    "type": "mcp_toolset",
                    "mcp_server_name": server["name"],
                }
                for server in native_mcp_servers
            )
        if extra.get("enable_compaction", True):
            edit: Dict[str, object] = {"type": "compact_20260112"}
            trigger_value = int(extra.get("compact_threshold", 150000))
            edit["trigger"] = {"type": "input_tokens", "value": trigger_value}
            if extra.get("pause_after_compaction"):
                edit["pause_after_compaction"] = True
            if extra.get("compaction_instructions"):
                edit["instructions"] = str(extra["compaction_instructions"])
            payload["context_management"] = {"edits": [edit]}
        betas: list[str] = []
        if extra.get("enable_compaction", True):
            betas.append("compact-2026-01-12")
        if native_mcp_servers:
            betas.append("mcp-client-2025-11-20")
        headers = {"anthropic-beta": ",".join(betas)} if betas else {}
        return ProviderRequest(
            provider=ProviderType.ANTHROPIC,
            endpoint_style="messages",
            path="/v1/messages",
            payload=payload,
            headers=headers,
            diagnostics={
                "stable_prefix_hash": assembly.provider_hints.get("stable_prefix_hash"),
                "cache_mode": "top_level_automatic_caching",
            },
        )
