from __future__ import annotations

import json

from multi_vendor_skills.models import RenderedArtifact, SkillDefinition
from multi_vendor_skills.renderers.base import SkillRenderer


class AnthropicToolsRenderer(SkillRenderer):
    """Render Anthropic/Messages API style tools.

    Suitable for Anthropic-compatible providers such as MiniMax's Anthropic endpoint.
    """

    def __init__(self, output_path: str = "anthropic-tools.json") -> None:
        self.output_path = output_path

    def render(self, skill: SkillDefinition) -> list[RenderedArtifact]:
        skill.validate()
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in skill.tools
        ]
        return [
            RenderedArtifact.text(
                self.output_path,
                json.dumps(tools, indent=2, ensure_ascii=False) + "\n",
            )
        ]
