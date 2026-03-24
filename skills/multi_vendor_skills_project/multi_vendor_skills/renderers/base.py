from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from multi_vendor_skills.models import RenderedArtifact, SkillDefinition


class SkillRenderer(ABC):
    @abstractmethod
    def render(self, skill: SkillDefinition) -> list[RenderedArtifact]:
        raise NotImplementedError

    def render_many(self, skills: Iterable[SkillDefinition]) -> list[RenderedArtifact]:
        output: list[RenderedArtifact] = []
        for skill in skills:
            output.extend(self.render(skill))
        return output
