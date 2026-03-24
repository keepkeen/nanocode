from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Optional

from .models import CachePlan, CompressionResult, MemoryRecord, Message, ProviderRequest, ToolSchema


class BaseProviderAdapter(ABC):
    @abstractmethod
    def build_request(
        self,
        *,
        model: str,
        cache_plan: CachePlan,
        tools: Optional[List[ToolSchema]] = None,
        extra: Optional[Dict[str, object]] = None,
    ) -> ProviderRequest:
        raise NotImplementedError


class BaseMemoryStore(ABC):
    @abstractmethod
    def add_message(self, message: Message, namespace: str = "default") -> None:
        raise NotImplementedError

    @abstractmethod
    def add_memory(self, memory: MemoryRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_messages(self, namespace: str = "default") -> List[Message]:
        raise NotImplementedError

    @abstractmethod
    def list_memories(self, namespace: str = "default") -> List[MemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    def upsert_memories(self, memories: Iterable[MemoryRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def tombstone_memory(self, memory_id: str, namespace: str = "default") -> None:
        raise NotImplementedError


class BaseCompressor(ABC):
    @abstractmethod
    def compress(
        self,
        *,
        namespace: str,
        messages: List[Message],
        existing_memories: List[MemoryRecord],
    ) -> CompressionResult:
        raise NotImplementedError


class BaseCachePlanner(ABC):
    @abstractmethod
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
        raise NotImplementedError


class BaseMemoryManager(ABC):
    @abstractmethod
    def ingest_message(self, message: Message) -> None:
        raise NotImplementedError

    @abstractmethod
    def prepare_request(self, *, provider_name: str, model: str, user_message: str) -> ProviderRequest:
        raise NotImplementedError

    @abstractmethod
    def compact(self) -> CompressionResult:
        raise NotImplementedError
