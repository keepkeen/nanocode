from __future__ import annotations

from typing import List

from .base import BaseCompactor
from .models import BlockKind, BlockPlane, EventRecord, MemoryBlock, MessageRole
from .store import EventSourcedMemoryStore
from .utils import first_sentence, top_terms


class ReversibleDeltaCompactor(BaseCompactor):
    """Prompt compaction without deleting truth.

    The event log remains append-only.
    Compaction only creates summary / episode blocks that *reference* old events.
    """

    def __init__(self, store: EventSourcedMemoryStore, *, keep_recent_events: int = 10, max_bullets: int = 8) -> None:
        self.store = store
        self.keep_recent_events = keep_recent_events
        self.max_bullets = max_bullets

    def compact(self, *, namespace: str) -> List[MemoryBlock]:
        events = self.store.list_events(namespace)
        if len(events) <= self.keep_recent_events:
            return []

        old_events = events[:-self.keep_recent_events]
        bullets = []
        seen = set()
        for ev in old_events:
            bullet = self._bullet(ev)
            if bullet and bullet not in seen:
                bullets.append(bullet)
                seen.add(bullet)
            if len(bullets) >= self.max_bullets:
                break

        if not bullets:
            return []

        summary_text = "[DELTA_SUMMARY]\n" + "\n".join(f"- {b}" for b in bullets)
        summary_block = MemoryBlock(
            namespace=namespace,
            plane=BlockPlane.DERIVED,
            kind=BlockKind.SUMMARY,
            text=summary_text,
            salience=0.72,
            stability=0.62,
            confidence=0.83,
            source_event_ids=[e.event_id for e in old_events],
            tags=top_terms(" ".join(bullets)),
            metadata={
                "summary_of": [e.event_id for e in old_events],
                "compaction_type": "reversible_delta",
            },
        )
        self.store.upsert_block(summary_block)
        return [summary_block]

    def _bullet(self, event: EventRecord) -> str:
        prefix = {
            MessageRole.SYSTEM: "System",
            MessageRole.DEVELOPER: "Developer",
            MessageRole.USER: "User",
            MessageRole.ASSISTANT: "Assistant",
            MessageRole.TOOL: "Tool",
            MessageRole.CACHE: "Cache",
        }[event.role]
        return f"{prefix}: {first_sentence(event.content, 180)}"
