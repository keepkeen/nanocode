from __future__ import annotations

from collections import OrderedDict
from typing import List, Sequence, Tuple

from .base import BaseCompressor
from .models import CompressionResult, MemoryKind, MemoryRecord, MemoryTier, Message, MessageRole


class RuleBasedDeltaCompressor(BaseCompressor):
    """A deterministic compressor designed for agent loops.

    Strategy:
    1. Keep the newest messages raw.
    2. Convert older stretches into a delta summary.
    3. Extract durable memories from facts, preferences, tasks, constraints, and decisions.
    4. Never rewrite stable system prefix here; that is handled by cache planning.
    """

    def __init__(self, keep_last_n_messages: int = 8, max_summary_bullets: int = 8) -> None:
        self.keep_last_n_messages = keep_last_n_messages
        self.max_summary_bullets = max_summary_bullets

    def compress(
        self,
        *,
        namespace: str,
        messages: List[Message],
        existing_memories: List[MemoryRecord],
    ) -> CompressionResult:
        if len(messages) <= self.keep_last_n_messages:
            return CompressionResult(
                summary="",
                compacted_messages=list(messages),
                extracted_memories=[],
                dropped_message_ids=[],
                stats={"compressed": False, "reason": "history_under_threshold"},
            )

        old_messages = messages[:-self.keep_last_n_messages]
        recent_messages = messages[-self.keep_last_n_messages :]

        summary = self._summarize_delta(old_messages)
        extracted = self._extract_memories(namespace=namespace, messages=old_messages)
        extracted = self._dedupe_against_existing(extracted, existing_memories)

        compacted_messages: List[Message] = []
        if summary:
            compacted_messages.append(
                Message(
                    role=MessageRole.SYSTEM,
                    content=(
                        "[COMPACTED_HISTORY]\n"
                        "This is a lossy but continuity-preserving summary of older turns.\n"
                        f"{summary}"
                    ),
                    metadata={"memory_tier": MemoryTier.COMPACTED.value},
                )
            )
        compacted_messages.extend(recent_messages)

        return CompressionResult(
            summary=summary,
            compacted_messages=compacted_messages,
            extracted_memories=extracted,
            dropped_message_ids=[m.message_id for m in old_messages],
            stats={
                "compressed": True,
                "messages_before": len(messages),
                "messages_after": len(compacted_messages),
                "extracted_memories": len(extracted),
            },
        )

    def _summarize_delta(self, messages: Sequence[Message]) -> str:
        bullets: List[str] = []
        seen = set()
        for msg in messages:
            line = self._message_to_bullet(msg)
            if not line or line in seen:
                continue
            bullets.append(line)
            seen.add(line)
            if len(bullets) >= self.max_summary_bullets:
                break
        return "\n".join(f"- {b}" for b in bullets)

    def _message_to_bullet(self, message: Message) -> str:
        text = " ".join(message.content.strip().split())
        if not text:
            return ""
        prefix = {
            MessageRole.SYSTEM: "System instruction",
            MessageRole.USER: "User asked",
            MessageRole.ASSISTANT: "Assistant responded",
            MessageRole.TOOL: "Tool returned",
            MessageRole.DEVELOPER: "Developer instruction",
        }[message.role]
        return f"{prefix}: {text[:180]}"

    def _extract_memories(self, *, namespace: str, messages: Sequence[Message]) -> List[MemoryRecord]:
        items: List[MemoryRecord] = []
        for msg in messages:
            if msg.role not in {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.SYSTEM, MessageRole.DEVELOPER}:
                continue
            if msg.metadata.get("memory_tier") == MemoryTier.COMPACTED.value:
                continue
            if msg.content.startswith("[COMPACTED_HISTORY]"):
                continue
            items.extend(self._extract_from_text(namespace=namespace, message=msg))
        return self._dedupe_within_batch(items)

    def _extract_from_text(self, *, namespace: str, message: Message) -> List[MemoryRecord]:
        text = " ".join(message.content.strip().split())
        lowered = text.lower()
        out: List[MemoryRecord] = []

        patterns: List[Tuple[str, MemoryKind, MemoryTier, float, float, str]] = [
            ("remember that", MemoryKind.FACT, MemoryTier.PINNED, 0.95, 0.95, "explicit remember cue"),
            ("my preference is", MemoryKind.PREFERENCE, MemoryTier.SEMANTIC, 0.8, 0.85, "explicit preference"),
            ("i prefer", MemoryKind.PREFERENCE, MemoryTier.SEMANTIC, 0.75, 0.8, "preference signal"),
            ("always ", MemoryKind.CONSTRAINT, MemoryTier.PINNED, 0.9, 0.9, "hard instruction"),
            ("never ", MemoryKind.CONSTRAINT, MemoryTier.PINNED, 0.9, 0.9, "hard instruction"),
            ("must ", MemoryKind.CONSTRAINT, MemoryTier.PINNED, 0.85, 0.85, "constraint cue"),
            ("todo", MemoryKind.TASK, MemoryTier.EPISODIC, 0.7, 0.65, "task cue"),
            ("next step", MemoryKind.TASK, MemoryTier.EPISODIC, 0.78, 0.7, "next-step cue"),
            ("decision:", MemoryKind.DECISION, MemoryTier.SEMANTIC, 0.8, 0.8, "decision cue"),
            ("artifact:", MemoryKind.ARTIFACT, MemoryTier.EPISODIC, 0.72, 0.7, "artifact cue"),
            ("environment:", MemoryKind.ENVIRONMENT, MemoryTier.SEMANTIC, 0.75, 0.78, "environment cue"),
        ]
        for needle, kind, tier, salience, durability, reason in patterns:
            if needle in lowered:
                out.append(
                    MemoryRecord(
                        text=text[:400],
                        kind=kind,
                        tier=tier,
                        salience=salience,
                        durability=durability,
                        namespace=namespace,
                        source_message_ids=[message.message_id],
                        tags=_simple_tags(text),
                        metadata={"write_reason": reason},
                    )
                )

        if message.role == MessageRole.USER and text.endswith(".") and len(text) < 180:
            factual_cues = ["i am ", "i use ", "we use ", "our stack", "my project", "working on"]
            if any(cue in lowered for cue in factual_cues):
                out.append(
                    MemoryRecord(
                        text=text,
                        kind=MemoryKind.FACT,
                        tier=MemoryTier.SEMANTIC,
                        salience=0.68,
                        durability=0.72,
                        namespace=namespace,
                        source_message_ids=[message.message_id],
                        tags=_simple_tags(text),
                        metadata={"write_reason": "lightweight factual cue"},
                    )
                )

        if message.role == MessageRole.ASSISTANT and ("summary" in lowered or "recap" in lowered):
            out.append(
                MemoryRecord(
                    text=text[:400],
                    kind=MemoryKind.SUMMARY,
                    tier=MemoryTier.COMPACTED,
                    salience=0.55,
                    durability=0.6,
                    namespace=namespace,
                    source_message_ids=[message.message_id],
                    tags=["summary"],
                    metadata={"write_reason": "assistant summary"},
                )
            )

        return out

    def _dedupe_against_existing(
        self,
        candidates: Sequence[MemoryRecord],
        existing_memories: Sequence[MemoryRecord],
    ) -> List[MemoryRecord]:
        existing_texts = {normalize_memory_text(m.text) for m in existing_memories if not m.tombstoned}
        return [m for m in candidates if normalize_memory_text(m.text) not in existing_texts]

    def _dedupe_within_batch(self, candidates: Sequence[MemoryRecord]) -> List[MemoryRecord]:
        ordered: "OrderedDict[str, MemoryRecord]" = OrderedDict()
        for item in candidates:
            key = normalize_memory_text(item.text)
            incumbent = ordered.get(key)
            if incumbent is None or (item.salience + item.durability) > (incumbent.salience + incumbent.durability):
                ordered[key] = item
        return list(ordered.values())


def normalize_memory_text(text: str) -> str:
    return " ".join(text.lower().split())


STOP_TAGS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "that", "this", "is", "are",
    "be", "as", "it", "we", "i", "you", "they", "he", "she", "at", "by", "from", "our", "my", "your",
}


def _simple_tags(text: str) -> List[str]:
    terms = ["".join(ch.lower() if ch.isalnum() else " " for ch in text).split()]
    flat = terms[0] if terms else []
    uniq: List[str] = []
    seen = set()
    for term in flat:
        if len(term) < 3 or term in STOP_TAGS or term in seen:
            continue
        seen.add(term)
        uniq.append(term)
        if len(uniq) >= 8:
            break
    return uniq
