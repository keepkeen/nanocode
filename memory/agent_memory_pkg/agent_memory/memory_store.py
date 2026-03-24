from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List

from .base import BaseMemoryStore
from .models import MemoryRecord, Message


class InMemoryMemoryStore(BaseMemoryStore):
    def __init__(self) -> None:
        self._messages: Dict[str, List[Message]] = defaultdict(list)
        self._memories: Dict[str, List[MemoryRecord]] = defaultdict(list)

    def add_message(self, message: Message, namespace: str = "default") -> None:
        self._messages[namespace].append(message)

    def add_memory(self, memory: MemoryRecord) -> None:
        self._memories[memory.namespace].append(memory)

    def list_messages(self, namespace: str = "default") -> List[Message]:
        return list(self._messages.get(namespace, []))

    def list_memories(self, namespace: str = "default") -> List[MemoryRecord]:
        return [m for m in self._memories.get(namespace, []) if not m.tombstoned]

    def upsert_memories(self, memories: Iterable[MemoryRecord]) -> None:
        for memory in memories:
            bucket = self._memories[memory.namespace]
            idx = next((i for i, item in enumerate(bucket) if item.memory_id == memory.memory_id), None)
            if idx is None:
                bucket.append(memory)
                continue
            bucket[idx] = memory

    def tombstone_memory(self, memory_id: str, namespace: str = "default") -> None:
        for memory in self._memories.get(namespace, []):
            if memory.memory_id == memory_id:
                memory.tombstoned = True
                break
