from __future__ import annotations

from multi_vendor_skills.models import RenderedArtifact, SkillDefinition
from multi_vendor_skills.renderers.base import SkillRenderer
from multi_vendor_skills.yaml_utils import dump_yaml


class ClaudeSubagentRenderer(SkillRenderer):
    """Render a Claude Code subagent markdown file.

    This is not identical to Agent Skills, but it is an official Claude Code reusable workflow format.
    """

    def __init__(self, tools: list[str] | None = None, root_prefix: str = ".claude/agents") -> None:
        self.tools = tools or []
        self.root_prefix = root_prefix.strip("/")

    def render(self, skill: SkillDefinition) -> list[RenderedArtifact]:
        skill.validate()
        frontmatter: dict[str, object] = {
            "name": skill.name,
            "description": skill.description,
        }
        if self.tools:
            frontmatter["tools"] = ", ".join(self.tools)

        body = (
            "---\n"
            + dump_yaml(frontmatter)
            + "\n---\n\n"
            + skill.instructions.strip()
            + "\n"
        )
        return [RenderedArtifact.text(f"{self.root_prefix}/{skill.name}.md", body)]
