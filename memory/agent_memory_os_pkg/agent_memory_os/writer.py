from __future__ import annotations

from typing import List
import re

from .base import BaseMemoryWriter
from .models import BlockKind, BlockPlane, EventRecord, MemoryBlock, MessageRole
from .utils import first_sentence, top_terms

PATH_RE = re.compile(r"(?:/[^\s]+)+|(?:[A-Za-z]:\\[^\s]+)")
URL_RE = re.compile(r"https?://\S+")


class FirstPrinciplesMemoryWriter(BaseMemoryWriter):
    """Decides what should become durable memory based on future utility.

    Heuristic routing policy:
    - behavior-shaping -> CONTROL
    - durable world/user/project fact -> DERIVED
    - current task cursor / TODO / next step -> EXECUTION
    - everything else stays in event log only
    """

    def derive_blocks(self, namespace: str, event: EventRecord) -> List[MemoryBlock]:
        text = event.content.strip()
        lowered = text.lower()
        blocks: List[MemoryBlock] = []

        if event.role in {MessageRole.SYSTEM, MessageRole.DEVELOPER}:
            blocks.append(
                MemoryBlock(
                    namespace=namespace,
                    plane=BlockPlane.CONTROL,
                    kind=BlockKind.POLICY,
                    text=first_sentence(text, 400),
                    salience=0.95,
                    stability=0.98,
                    confidence=0.95,
                    source_event_ids=[event.event_id],
                    tags=top_terms(text),
                    metadata={"write_reason": "system_or_developer_policy"},
                )
            )
            return blocks

        if any(cue in lowered for cue in ["always ", "never ", "must ", "do not ", "don't "]):
            blocks.append(
                MemoryBlock(
                    namespace=namespace,
                    plane=BlockPlane.CONTROL,
                    kind=BlockKind.CONSTRAINT,
                    text=first_sentence(text, 320),
                    salience=0.92,
                    stability=0.95,
                    confidence=0.88,
                    source_event_ids=[event.event_id],
                    tags=top_terms(text),
                    metadata={"write_reason": "hard_constraint"},
                )
            )

        if any(cue in lowered for cue in ["i prefer", "my preference", "prefer ", "style:", "coding style"]):
            blocks.append(
                MemoryBlock(
                    namespace=namespace,
                    plane=BlockPlane.DERIVED,
                    kind=BlockKind.PREFERENCE,
                    text=first_sentence(text, 320),
                    salience=0.82,
                    stability=0.86,
                    confidence=0.78,
                    source_event_ids=[event.event_id],
                    tags=top_terms(text),
                    metadata={"write_reason": "user_preference"},
                )
            )

        if any(cue in lowered for cue in ["decision:", "we decided", "let's use", "we will use"]):
            blocks.append(
                MemoryBlock(
                    namespace=namespace,
                    plane=BlockPlane.DERIVED,
                    kind=BlockKind.DECISION,
                    text=first_sentence(text, 360),
                    salience=0.84,
                    stability=0.8,
                    confidence=0.8,
                    source_event_ids=[event.event_id],
                    tags=top_terms(text),
                    metadata={"write_reason": "decision_signal"},
                )
            )

        if any(cue in lowered for cue in ["todo", "next step", "remaining work", "pending", "open issue"]):
            blocks.append(
                MemoryBlock(
                    namespace=namespace,
                    plane=BlockPlane.EXECUTION,
                    kind=BlockKind.TASK_STATE,
                    text=first_sentence(text, 360),
                    salience=0.8,
                    stability=0.45,
                    confidence=0.72,
                    source_event_ids=[event.event_id],
                    tags=top_terms(text),
                    metadata={"write_reason": "task_cursor"},
                )
            )

        if event.role == MessageRole.USER and len(text) < 220 and any(cue in lowered for cue in ["we use", "our stack", "project", "repo", "path", "i am using"]):
            blocks.append(
                MemoryBlock(
                    namespace=namespace,
                    plane=BlockPlane.DERIVED,
                    kind=BlockKind.FACT,
                    text=first_sentence(text, 300),
                    salience=0.76,
                    stability=0.7,
                    confidence=0.76,
                    source_event_ids=[event.event_id],
                    tags=top_terms(text),
                    metadata={"write_reason": "durable_fact"},
                )
            )

        refs = PATH_RE.findall(text) + URL_RE.findall(text)
        if refs:
            blocks.append(
                MemoryBlock(
                    namespace=namespace,
                    plane=BlockPlane.DERIVED,
                    kind=BlockKind.ARTIFACT_REF,
                    text=first_sentence(text, 360),
                    salience=0.7,
                    stability=0.65,
                    confidence=0.72,
                    source_event_ids=[event.event_id],
                    tags=top_terms(text),
                    references=refs[:8],
                    metadata={"write_reason": "artifact_reference"},
                )
            )

        if event.role == MessageRole.TOOL and len(text) < 500:
            blocks.append(
                MemoryBlock(
                    namespace=namespace,
                    plane=BlockPlane.EVIDENCE,
                    kind=BlockKind.EPISODE,
                    text=first_sentence(text, 420),
                    salience=0.62,
                    stability=0.4,
                    confidence=0.85,
                    source_event_ids=[event.event_id],
                    tags=top_terms(text),
                    references=refs[:8],
                    metadata={"write_reason": "tool_observation"},
                )
            )

        return self._dedupe(blocks)

    def _dedupe(self, blocks: List[MemoryBlock]) -> List[MemoryBlock]:
        seen = {}
        for block in blocks:
            key = (block.plane.value, block.kind.value, block.text.lower())
            incumbent = seen.get(key)
            if incumbent is None or (block.salience + block.stability) > (incumbent.salience + incumbent.stability):
                seen[key] = block
        return list(seen.values())
