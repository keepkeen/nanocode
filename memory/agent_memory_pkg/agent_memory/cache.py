from __future__ import annotations

from typing import Dict, List, Optional

from .base import BaseCachePlanner
from .models import CachePlan, MemoryRecord, MemoryTier, Message, MessageRole, ToolSchema, canonical_message_fingerprint


class PrefixStableCachePlanner(BaseCachePlanner):
    """Plans prompts for maximum cache hits and memory retention.

    Core policy:
    - Stable prefix first: system instructions, tool definitions, pinned memories.
    - Retrieved semantic memory next.
    - Episodic summaries after semantic memory.
    - Dynamic content only at the tail.
    - Avoid injecting dynamic tool output into the stable prefix.
    """

    def __init__(
        self,
        *,
        max_memory_messages: int = 8,
        max_recent_messages: int = 8,
        include_tool_manifest_message: bool = True,
    ) -> None:
        self.max_memory_messages = max_memory_messages
        self.max_recent_messages = max_recent_messages
        self.include_tool_manifest_message = include_tool_manifest_message

    def plan(
        self,
        *,
        query: str,
        system_messages: List[Message],
        pinned_messages: List[Message],
        memories: List[MemoryRecord],
        recent_messages: List[Message],
        tool_schemas: Optional[List[ToolSchema]] = None,
        provider_name: Optional[str] = None,
        namespace: str = "default",
    ) -> CachePlan:
        ranked_memories = sorted(memories, key=lambda m: m.retrieval_score(query), reverse=True)

        pinned_memories = [m for m in ranked_memories if m.tier in {MemoryTier.INSTRUCTION, MemoryTier.PINNED}]
        semantic_memories = [m for m in ranked_memories if m.tier == MemoryTier.SEMANTIC]
        episodic_memories = [m for m in ranked_memories if m.tier in {MemoryTier.EPISODIC, MemoryTier.COMPACTED}]

        stable_prefix: List[Message] = []
        stable_prefix.extend(system_messages)
        if tool_schemas and self.include_tool_manifest_message:
            stable_prefix.append(self._build_tool_manifest(tool_schemas))
        stable_prefix.extend(pinned_messages)
        stable_prefix.extend(self._memory_records_to_messages(pinned_memories[:3], title="Pinned memory"))
        stable_prefix.extend(self._memory_records_to_messages(semantic_memories[:3], title="Semantic memory"))

        memory_injection: List[Message] = []
        remaining_slots = max(0, self.max_memory_messages - 6)
        memory_injection.extend(self._memory_records_to_messages(episodic_memories[:remaining_slots], title="Episodic memory"))

        dynamic_tail = recent_messages[-self.max_recent_messages :]

        prefix_fp = canonical_message_fingerprint(stable_prefix)
        provider_hints = self._provider_hints(
            provider_name=provider_name or "generic",
            namespace=namespace,
            prefix_fingerprint=prefix_fp,
            tool_schemas=tool_schemas or [],
        )

        return CachePlan(
            stable_prefix=stable_prefix,
            memory_injection=memory_injection,
            dynamic_tail=dynamic_tail,
            provider_hints=provider_hints,
            diagnostics={
                "stable_prefix_messages": len(stable_prefix),
                "memory_injection_messages": len(memory_injection),
                "dynamic_tail_messages": len(dynamic_tail),
                "selected_pinned": [m.memory_id for m in pinned_memories[:3]],
                "selected_semantic": [m.memory_id for m in semantic_memories[:3]],
                "selected_episodic": [m.memory_id for m in episodic_memories[:remaining_slots]],
                "prefix_fingerprint": prefix_fp,
            },
        )

    def _memory_records_to_messages(self, memories: List[MemoryRecord], *, title: str) -> List[Message]:
        if not memories:
            return []
        lines = [f"- [{m.kind.value}/{m.tier.value}] {m.text}" for m in memories]
        return [
            Message(
                role=MessageRole.SYSTEM,
                content=f"[{title}]\n" + "\n".join(lines),
                metadata={"memory_bundle": title.lower().replace(" ", "_")},
            )
        ]

    def _build_tool_manifest(self, tools: List[ToolSchema]) -> Message:
        lines = [f"- {tool.name}: {tool.description} (schema_hash={tool.stable_hash()})" for tool in tools]
        return Message(
            role=MessageRole.SYSTEM,
            content="[Stable tool manifest]\n" + "\n".join(lines),
            metadata={"stable_tool_manifest": True},
        )

    def _provider_hints(
        self,
        *,
        provider_name: str,
        namespace: str,
        prefix_fingerprint: str,
        tool_schemas: List[ToolSchema],
    ) -> Dict[str, object]:
        tool_hashes = [tool.stable_hash() for tool in tool_schemas]
        cache_namespace = f"{provider_name}:{namespace}:{prefix_fingerprint[:12]}"
        hints: Dict[str, object] = {
            "cache_namespace": cache_namespace,
            "prefix_fingerprint": prefix_fingerprint,
            "tool_hashes": tool_hashes,
            "policy": {
                "dynamic_content_in_tail": True,
                "exclude_dynamic_tool_results_from_prefix": True,
                "stable_prefix_first": True,
            },
        }
        if provider_name == "openai":
            hints.update(
                {
                    "prompt_cache_key": cache_namespace,
                    "prompt_cache_retention": "24h",
                }
            )
        elif provider_name == "anthropic":
            hints.update(
                {
                    "cache_control": {"type": "ephemeral"},
                    "breakpoint_strategy": "after_stable_prefix",
                }
            )
        elif provider_name == "kimi":
            hints.update(
                {
                    "kimi_context_cache_key": cache_namespace,
                    "kimi_context_cache_ttl_seconds": 3600,
                }
            )
        elif provider_name in {"deepseek", "glm", "minimax"}:
            hints.update(
                {
                    "implicit_prefix_cache": True,
                    "prefix_stability_required": True,
                }
            )
        return hints
