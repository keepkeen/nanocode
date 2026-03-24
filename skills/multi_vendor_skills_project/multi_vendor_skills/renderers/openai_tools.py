from __future__ import annotations

import json

from multi_vendor_skills.models import RenderedArtifact, SkillDefinition
from multi_vendor_skills.renderers.base import SkillRenderer


class OpenAICompatibleToolsRenderer(SkillRenderer):
    """Render OpenAI-compatible tool/function definitions.

    Suitable for providers whose chat-completions API accepts
    tools=[{"type": "function", "function": {...}}].
    """

    def __init__(self, output_path: str = "tools.json") -> None:
        self.output_path = output_path

    def function_object(self, skill: SkillDefinition) -> list[dict]:
        skill.validate()
        tools: list[dict] = []
        for tool in skill.tools:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return tools

    def render(self, skill: SkillDefinition) -> list[RenderedArtifact]:
        return [
            RenderedArtifact.text(
                self.output_path,
                json.dumps(self.function_object(skill), indent=2, ensure_ascii=False) + "\n",
            )
        ]


class DeepSeekToolsRenderer(OpenAICompatibleToolsRenderer):
    """DeepSeek adds an optional strict=true flag per function in beta mode."""

    def function_object(self, skill: SkillDefinition) -> list[dict]:
        base = super().function_object(skill)
        for tool_dict, tool in zip(base, skill.tools, strict=True):
            if tool.strict:
                tool_dict["function"]["strict"] = True
        return base
