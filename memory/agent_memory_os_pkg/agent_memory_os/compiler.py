from __future__ import annotations

from typing import List

from .base import BaseContextCompiler
from .models import BlockKind, BlockPlane, ContextAssembly, ContextZone, MemoryBlock, Message, MessageRole, RetrievalHit, ToolSchema
from .store import EventSourcedMemoryStore
from .utils import content_address


class CacheSafeContextCompiler(BaseContextCompiler):
    def __init__(self, store: EventSourcedMemoryStore, *, recent_turns: int = 8) -> None:
        self.store = store
        self.recent_turns = recent_turns

    def compile(
        self,
        *,
        namespace: str,
        query: str,
        user_message: Message,
        retrieved: List[RetrievalHit],
        tools: List[ToolSchema],
    ) -> ContextAssembly:
        control_blocks = self._sorted_control_blocks(namespace)
        stable_control_zone = ContextZone(
            name="stable_control",
            messages=[self._block_to_system_message(b) for b in control_blocks],
            stable=True,
            notes="Canonical control-plane blocks for cache-safe prefix reuse.",
        )

        tool_zone = ContextZone(
            name="tool_manifest",
            messages=[self._tool_manifest_message(tools)] if tools else [],
            stable=True,
            notes="Stable tool manifest. Changes here invalidate downstream cache.",
        )

        scoped_blocks = [h.block for h in retrieved if h.block.plane != BlockPlane.CONTROL][:6]
        scoped_zone = ContextZone(
            name="retrieved_memory",
            messages=[self._block_to_context_message(b, heading="MEMORY_CONTEXT") for b in scoped_blocks],
            stable=False,
            notes="Query-scoped memory bundle. Intentionally outside stable prefix.",
        )

        execution_zone = ContextZone(
            name="execution_state",
            messages=self._execution_messages(namespace),
            stable=False,
            notes="Ephemeral task cursor and current execution state.",
        )

        recent_zone = ContextZone(
            name="recent_turns",
            messages=self._recent_messages(namespace),
            stable=False,
            notes="Newest raw turns kept verbatim for locality.",
        )

        final_user_zone = ContextZone(
            name="new_user_turn",
            messages=[user_message],
            stable=False,
            notes="Current user turn must remain at the dynamic tail.",
        )

        zones = [stable_control_zone, tool_zone, scoped_zone, execution_zone, recent_zone, final_user_zone]
        stable_prefix_hash = content_address([m.to_openai_dict() for m in stable_control_zone.messages + tool_zone.messages])
        return ContextAssembly(
            zones=zones,
            provider_hints={
                "stable_prefix_hash": stable_prefix_hash,
                "query": query,
                "zone_order": [z.name for z in zones],
            },
            diagnostics={
                "stable_prefix_tokens": sum(z.approx_tokens() for z in zones if z.stable),
                "dynamic_tokens": sum(z.approx_tokens() for z in zones if not z.stable),
                "retrieved_block_ids": [b.block_id for b in scoped_blocks],
            },
        )

    def _sorted_control_blocks(self, namespace: str) -> List[MemoryBlock]:
        blocks = [b for b in self.store.list_control_blocks(namespace) if b.active]
        priority = {
            BlockKind.POLICY: 0,
            BlockKind.TOOL_MANIFEST: 1,
            BlockKind.CONSTRAINT: 2,
            BlockKind.PREFERENCE: 3,
            BlockKind.STYLE: 4,
            BlockKind.FACT: 5,
        }
        return sorted(
            blocks,
            key=lambda b: (
                priority.get(b.kind, 99),
                -b.stability,
                b.address(),
            ),
        )

    def _tool_manifest_message(self, tools: List[ToolSchema]) -> Message:
        lines = [f"- {tool.name}: {tool.description} (schema_hash={tool.stable_hash()})" for tool in tools]
        return Message(
            role=MessageRole.SYSTEM,
            content="[STABLE_TOOL_MANIFEST]\n" + "\n".join(lines),
            metadata={"stable_tool_manifest": True},
        )

    def _block_to_system_message(self, block: MemoryBlock) -> Message:
        return Message(
            role=MessageRole.SYSTEM,
            content=f"[{block.kind.value.upper()}|{block.plane.value}] {block.text}",
            metadata={
                "block_id": block.block_id,
                "block_kind": block.kind.value,
                "block_plane": block.plane.value,
            },
        )

    def _execution_messages(self, namespace: str) -> List[Message]:
        blocks = self.store.list_execution_blocks(namespace)
        if not blocks:
            return []
        ranked = sorted(blocks, key=lambda b: (-b.salience, -b.created_at.timestamp()))[:3]
        return [self._block_to_context_message(b, heading="EXECUTION_STATE") for b in ranked]

    def _recent_messages(self, namespace: str) -> List[Message]:
        events = [e for e in self.store.list_events(namespace) if e.role not in {MessageRole.SYSTEM, MessageRole.DEVELOPER}][-self.recent_turns :]
        return [Message(role=e.role, content=e.content, metadata=e.metadata) for e in events]

    def _block_to_context_message(self, block: MemoryBlock, heading: str) -> Message:
        return Message(
            role=MessageRole.USER,
            content=f"[{heading}] [{block.kind.value}/{block.plane.value}] {block.text}",
            metadata={"block_id": block.block_id, "context_heading": heading},
        )
