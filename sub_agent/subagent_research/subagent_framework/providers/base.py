from __future__ import annotations

from abc import ABC, abstractmethod

from ..abstractions import AbstractProviderAdapter
from ..models import ProviderArtifact, SubAgentDefinition


class BaseProviderAdapter(AbstractProviderAdapter, ABC):
    provider_name: str = "base"

    @abstractmethod
    def build_artifact(self, definition: SubAgentDefinition, sample_task: str) -> ProviderArtifact:
        raise NotImplementedError
