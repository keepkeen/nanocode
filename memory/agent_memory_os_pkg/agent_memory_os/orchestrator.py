from __future__ import annotations

from typing import Dict, List, Optional

from .compaction import ReversibleDeltaCompactor
from .compiler import CacheSafeContextCompiler
from .models import BlockKind, BlockPlane, EventRecord, MemoryBlock, Message, MessageRole, ProviderRequest, ToolSchema
from .providers import build_default_adapters
from .store import EventSourcedMemoryStore
from .writer import FirstPrinciplesMemoryWriter
from .indexing import HybridRetriever


class AgentMemoryOS:
    def __init__(
        self,
        *,
        namespace: str = "default",
        store: Optional[EventSourcedMemoryStore] = None,
        writer: Optional[FirstPrinciplesMemoryWriter] = None,
        recent_turns: int = 8,
        compaction_event_threshold: int = 18,
        adapters: Optional[Dict[str, object]] = None,
    ) -> None:
        self.namespace = namespace
        self.store = store or EventSourcedMemoryStore()
        self.writer = writer or FirstPrinciplesMemoryWriter()
        self.retriever = HybridRetriever(self.store)
        self.compactor = ReversibleDeltaCompactor(self.store)
        self.compiler = CacheSafeContextCompiler(self.store, recent_turns=recent_turns)
        self.compaction_event_threshold = compaction_event_threshold
        self.adapters = adapters or build_default_adapters()
        self._tools: List[ToolSchema] = []

    def set_system_policies(self, policies: List[str]) -> None:
        for text in policies:
            self.observe(Message(role=MessageRole.SYSTEM, content=text))

    def add_user_instruction(self, text: str) -> None:
        self.observe(Message(role=MessageRole.DEVELOPER, content=text))

    def register_tools(self, tools: List[ToolSchema]) -> None:
        self._tools = list(tools)

    def observe(self, message: Message, source: str = "conversation") -> None:
        event = EventRecord(
            namespace=self.namespace,
            role=message.role,
            content=message.content,
            source=source,
            metadata=message.metadata,
        )
        self.store.append_event(event)
        blocks = self.writer.derive_blocks(self.namespace, event)
        for block in blocks:
            self._merge_block(block)
        if len(self.store.list_events(self.namespace)) >= self.compaction_event_threshold:
            self.compact()

    def _merge_block(self, block: MemoryBlock) -> None:
        # Simple supersession policy: replace same plane+kind with same normalized text prefix if new block is stronger.
        existing = self.store.list_blocks(self.namespace)
        target = None
        for prior in existing:
            if prior.plane == block.plane and prior.kind == block.kind and prior.text.lower() == block.text.lower():
                target = prior
                break
        if target is None:
            self.store.upsert_block(block)
            return
        if (block.salience + block.stability) >= (target.salience + target.stability):
            self.store.supersede_block(target.block_id, block)

    def compact(self) -> List[MemoryBlock]:
        return self.compactor.compact(namespace=self.namespace)

    def retrieve(self, query: str, top_k: int = 8):
        return self.retriever.retrieve(namespace=self.namespace, query=query, top_k=top_k)

    def prepare_request(
        self,
        *,
        provider_name: str,
        model: str,
        user_message: str,
        top_k: int = 8,
        extra: Optional[Dict[str, object]] = None,
    ) -> ProviderRequest:
        user_msg = Message(role=MessageRole.USER, content=user_message)
        retrieved = self.retrieve(user_message, top_k=top_k)
        assembly = self.compiler.compile(
            namespace=self.namespace,
            query=user_message,
            user_message=user_msg,
            retrieved=retrieved,
            tools=self._tools,
        )
        adapter = self.adapters[provider_name]
        request = adapter.build_request(model=model, assembly=assembly, tools=self._tools, extra=extra or {})
        request.diagnostics.setdefault("retrieval", [])
        request.diagnostics["retrieval"] = [
            {
                "block_id": hit.block.block_id,
                "plane": hit.block.plane.value,
                "kind": hit.block.kind.value,
                "score": round(hit.score, 4),
                "channels": {k: round(v, 4) for k, v in hit.channel_scores.items()},
            }
            for hit in retrieved
        ]
        request.diagnostics["context"] = assembly.diagnostics
        return request

    def export_state(self) -> Dict[str, object]:
        return {
            "namespace": self.namespace,
            "events": [
                {
                    "event_id": e.event_id,
                    "role": e.role.value,
                    "content": e.content,
                    "source": e.source,
                }
                for e in self.store.list_events(self.namespace)
            ],
            "blocks": [
                {
                    "block_id": b.block_id,
                    "plane": b.plane.value,
                    "kind": b.kind.value,
                    "text": b.text,
                    "salience": b.salience,
                    "stability": b.stability,
                    "confidence": b.confidence,
                    "active": b.active,
                }
                for b in self.store.list_blocks(self.namespace, active_only=False)
            ],
        }

    def control_blocks(self) -> List[MemoryBlock]:
        return self.store.list_control_blocks(self.namespace)

    def all_blocks(self) -> List[MemoryBlock]:
        return self.store.list_blocks(self.namespace, active_only=False)
