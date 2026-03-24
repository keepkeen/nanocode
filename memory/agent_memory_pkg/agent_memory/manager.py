from __future__ import annotations

from typing import Dict, List, Optional

from .base import BaseMemoryManager
from .cache import PrefixStableCachePlanner
from .compression import RuleBasedDeltaCompressor
from .memory_store import InMemoryMemoryStore
from .models import CompressionResult, MemoryKind, MemoryRecord, MemoryTier, Message, MessageRole, ProviderRequest, ToolSchema
from .providers import build_default_adapters


class HierarchicalMemoryManager(BaseMemoryManager):
    """Reference implementation of a cache-friendly, memory-retaining agent memory layer.

    Design goals:
    - maximize prefix cache hits by keeping the stable prefix unchanged
    - preserve durable memory through hierarchical storage and delta compaction
    - keep provider-specific details out of core memory logic
    """

    def __init__(
        self,
        *,
        namespace: str = "default",
        store: Optional[InMemoryMemoryStore] = None,
        compressor: Optional[RuleBasedDeltaCompressor] = None,
        cache_planner: Optional[PrefixStableCachePlanner] = None,
        adapters: Optional[Dict[str, object]] = None,
        compaction_trigger_messages: int = 18,
    ) -> None:
        self.namespace = namespace
        self.store = store or InMemoryMemoryStore()
        self.compressor = compressor or RuleBasedDeltaCompressor()
        self.cache_planner = cache_planner or PrefixStableCachePlanner()
        self.adapters = adapters or build_default_adapters()
        self.compaction_trigger_messages = compaction_trigger_messages
        self._system_messages: List[Message] = []
        self._pinned_messages: List[Message] = []
        self._tool_schemas: List[ToolSchema] = []

    def set_system_instructions(self, instructions: List[str]) -> None:
        self._system_messages = [Message(role=MessageRole.SYSTEM, content=text) for text in instructions]

    def pin_instruction(self, text: str) -> None:
        self._pinned_messages.append(Message(role=MessageRole.SYSTEM, content=text, metadata={"pinned": True}))
        self.store.add_memory(
            MemoryRecord(
                text=text,
                kind=MemoryKind.CONSTRAINT,
                tier=MemoryTier.PINNED,
                salience=0.95,
                durability=0.95,
                namespace=self.namespace,
                tags=["pinned"],
                metadata={"source": "pin_instruction"},
            )
        )

    def register_tools(self, tool_schemas: List[ToolSchema]) -> None:
        self._tool_schemas = list(tool_schemas)

    def ingest_message(self, message: Message) -> None:
        self.store.add_message(message, namespace=self.namespace)
        if len(self.store.list_messages(self.namespace)) >= self.compaction_trigger_messages:
            self.compact()

    def retrieve_memories(self, query: str, top_k: int = 8) -> List[MemoryRecord]:
        memories = self.store.list_memories(self.namespace)
        ranked = sorted(memories, key=lambda m: m.retrieval_score(query), reverse=True)
        selected = ranked[:top_k]
        for item in selected:
            item.touch()
        return selected

    def prepare_request(self, *, provider_name: str, model: str, user_message: str) -> ProviderRequest:
        adapter = self.adapters[provider_name]
        recent_messages = self.store.list_messages(self.namespace)
        final_user = Message(role=MessageRole.USER, content=user_message)
        combined_recent = [*recent_messages, final_user]
        memories = self.retrieve_memories(user_message, top_k=8)
        cache_plan = self.cache_planner.plan(
            query=user_message,
            system_messages=self._system_messages,
            pinned_messages=self._pinned_messages,
            memories=memories,
            recent_messages=combined_recent,
            tool_schemas=self._tool_schemas,
            provider_name=provider_name,
            namespace=self.namespace,
        )
        request = adapter.build_request(
            model=model,
            cache_plan=cache_plan,
            tools=self._tool_schemas,
            extra={"enable_compaction": True},
        )
        request.diagnostics["memory_candidates"] = [
            {
                "memory_id": m.memory_id,
                "tier": m.tier.value,
                "kind": m.kind.value,
                "score": round(m.retrieval_score(user_message), 4),
            }
            for m in memories
        ]
        request.diagnostics["cache_plan"] = cache_plan.diagnostics
        return request

    def compact(self) -> CompressionResult:
        messages = self.store.list_messages(self.namespace)
        memories = self.store.list_memories(self.namespace)
        result = self.compressor.compress(namespace=self.namespace, messages=messages, existing_memories=memories)
        if not result.stats.get("compressed"):
            return result

        # Replace the stored message history with the compacted history.
        self.store._messages[self.namespace] = result.compacted_messages  # intentional internal reset for demo package
        self.store.upsert_memories(result.extracted_memories)
        return result

    def export_state(self) -> Dict[str, object]:
        return {
            "namespace": self.namespace,
            "system_messages": [m.to_openai_dict() for m in self._system_messages],
            "pinned_messages": [m.to_openai_dict() for m in self._pinned_messages],
            "messages": [m.to_openai_dict() for m in self.store.list_messages(self.namespace)],
            "memories": [
                {
                    "memory_id": m.memory_id,
                    "text": m.text,
                    "tier": m.tier.value,
                    "kind": m.kind.value,
                    "salience": m.salience,
                    "durability": m.durability,
                    "tags": m.tags,
                }
                for m in self.store.list_memories(self.namespace)
            ],
        }
