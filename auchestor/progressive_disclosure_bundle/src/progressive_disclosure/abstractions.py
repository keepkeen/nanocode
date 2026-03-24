from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

from .domain import DisclosureContext, DisclosureDecision, DisclosureMessage, EvidenceRef


class AbstractNoveltyGate(ABC):
    @abstractmethod
    def should_emit(self, context: DisclosureContext, decision: DisclosureDecision) -> bool:
        raise NotImplementedError

    @abstractmethod
    def record(self, context: DisclosureContext, message: DisclosureMessage) -> None:
        raise NotImplementedError


class AbstractDisclosurePolicy(ABC):
    @abstractmethod
    def decide(self, context: DisclosureContext) -> DisclosureDecision:
        raise NotImplementedError


class AbstractEvidenceSelector(ABC):
    @abstractmethod
    def select(self, context: DisclosureContext, decision: DisclosureDecision) -> Sequence[EvidenceRef]:
        raise NotImplementedError


class AbstractTraceProvider(ABC):
    @abstractmethod
    def select(self, context: DisclosureContext, decision: DisclosureDecision) -> Sequence[str]:
        raise NotImplementedError


class AbstractRenderer(ABC):
    @abstractmethod
    def render(
        self,
        context: DisclosureContext,
        decision: DisclosureDecision,
        evidence: Sequence[EvidenceRef],
        trace: Sequence[str],
    ) -> DisclosureMessage:
        raise NotImplementedError


class AbstractEventSink(ABC):
    @abstractmethod
    def publish(self, message: DisclosureMessage) -> None:
        raise NotImplementedError
