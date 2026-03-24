from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterable, List, Optional

from .models import ContextAssembly, EventRecord, MemoryBlock, Message, ProviderRequest, RetrievalHit, ToolSchema


class BaseEventStore(ABC):
    @abstractmethod
    def append_event(self, event: EventRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_block(self, block: MemoryBlock) -> None:
        raise NotImplementedError

    @abstractmethod
    def supersede_block(self, old_block_id: str, new_block: MemoryBlock) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_events(self, namespace: str) -> List[EventRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_blocks(self, namespace: str, active_only: bool = True) -> List[MemoryBlock]:
        raise NotImplementedError


class BaseMemoryWriter(ABC):
    @abstractmethod
    def derive_blocks(self, namespace: str, event: EventRecord) -> List[MemoryBlock]:
        raise NotImplementedError


class BaseRetriever(ABC):
    @abstractmethod
    def retrieve(self, *, namespace: str, query: str, top_k: int) -> List[RetrievalHit]:
        raise NotImplementedError


class BaseCompactor(ABC):
    @abstractmethod
    def compact(self, *, namespace: str) -> List[MemoryBlock]:
        raise NotImplementedError


class BaseContextCompiler(ABC):
    @abstractmethod
    def compile(
        self,
        *,
        namespace: str,
        query: str,
        user_message: Message,
        retrieved: List[RetrievalHit],
        tools: List[ToolSchema],
    ) -> ContextAssembly:
        raise NotImplementedError


class BaseProviderAdapter(ABC):
    @abstractmethod
    def build_request(
        self,
        *,
        model: str,
        assembly: ContextAssembly,
        tools: Optional[List[ToolSchema]] = None,
        extra: Optional[Dict[str, object]] = None,
    ) -> ProviderRequest:
        raise NotImplementedError


class BaseRuntime(ABC):
    @abstractmethod
    def invoke(self, request: ProviderRequest, *, api_key: str, base_url: Optional[str] = None) -> object:
        raise NotImplementedError
