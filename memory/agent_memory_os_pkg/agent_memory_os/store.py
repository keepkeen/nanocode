from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .base import BaseEventStore
from .models import BlockPlane, EventRecord, MemoryBlock


class EventSourcedMemoryStore(BaseEventStore):
    def __init__(self) -> None:
        self._events: Dict[str, List[EventRecord]] = defaultdict(list)
        self._blocks: Dict[str, List[MemoryBlock]] = defaultdict(list)
        self._execution_state: Dict[str, Dict[str, str]] = defaultdict(dict)

    def append_event(self, event: EventRecord) -> None:
        self._events[event.namespace].append(event)

    def upsert_block(self, block: MemoryBlock) -> None:
        bucket = self._blocks[block.namespace]
        for idx, existing in enumerate(bucket):
            if existing.block_id == block.block_id:
                bucket[idx] = block
                return
        bucket.append(block)

    def supersede_block(self, old_block_id: str, new_block: MemoryBlock) -> None:
        bucket = self._blocks[new_block.namespace]
        for block in bucket:
            if block.block_id == old_block_id:
                block.active = False
                break
        new_block.supersedes = old_block_id
        bucket.append(new_block)

    def list_events(self, namespace: str) -> List[EventRecord]:
        return list(self._events.get(namespace, []))

    def list_blocks(self, namespace: str, active_only: bool = True) -> List[MemoryBlock]:
        blocks = list(self._blocks.get(namespace, []))
        if active_only:
            blocks = [b for b in blocks if b.active]
        return blocks

    def list_control_blocks(self, namespace: str) -> List[MemoryBlock]:
        return [b for b in self.list_blocks(namespace) if b.plane == BlockPlane.CONTROL]

    def list_execution_blocks(self, namespace: str) -> List[MemoryBlock]:
        return [b for b in self.list_blocks(namespace) if b.plane == BlockPlane.EXECUTION]

    def set_execution_value(self, namespace: str, key: str, value: str) -> None:
        self._execution_state[namespace][key] = value

    def get_execution_state(self, namespace: str) -> Dict[str, str]:
        return dict(self._execution_state.get(namespace, {}))
