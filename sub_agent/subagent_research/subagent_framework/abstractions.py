from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List, Sequence

from .models import (
    DelegationDecision,
    ProviderArtifact,
    SubAgentDefinition,
    TaskEnvelope,
    TaskResult,
    WorkingMemorySnapshot,
)


class AbstractSubAgent(ABC):
    """Base contract for a concrete sub-agent implementation."""

    definition: SubAgentDefinition

    @abstractmethod
    def can_handle(self, task: TaskEnvelope) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def arun(
        self,
        task: TaskEnvelope,
        memory: WorkingMemorySnapshot,
    ) -> TaskResult:
        raise NotImplementedError


class AbstractProviderAdapter(ABC):
    """Serializes the canonical sub-agent spec into a vendor-native format."""

    provider_name: str

    @abstractmethod
    def build_artifact(self, definition: SubAgentDefinition, sample_task: str) -> ProviderArtifact:
        raise NotImplementedError


class AbstractRouter(ABC):
    @abstractmethod
    def decide(self, task: TaskEnvelope, agents: Sequence[AbstractSubAgent]) -> DelegationDecision:
        raise NotImplementedError


class AbstractMemory(ABC):
    @abstractmethod
    def remember(self, agent_name: str, subgoal: str, observation: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self, active_subgoal: str | None = None) -> WorkingMemorySnapshot:
        raise NotImplementedError
