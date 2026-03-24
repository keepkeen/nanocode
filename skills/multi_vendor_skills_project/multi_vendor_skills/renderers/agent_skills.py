from __future__ import annotations

from multi_vendor_skills.models import RenderedArtifact, SkillDefinition
from multi_vendor_skills.renderers.base import SkillRenderer
from multi_vendor_skills.yaml_utils import dump_yaml


class AgentSkillsRenderer(SkillRenderer):
    """Render a provider-neutral Agent Skills package.

    This matches the open SKILL.md-based format used by OpenAI Skills and Anthropic Skills.
    """

    def __init__(self, root_prefix: str = "") -> None:
        self.root_prefix = root_prefix.strip("/")

    def render(self, skill: SkillDefinition) -> list[RenderedArtifact]:
        skill.validate()
        prefix = f"{self.root_prefix}/" if self.root_prefix else ""
        base = f"{prefix}{skill.name}"

        frontmatter: dict[str, object] = {
            "name": skill.name,
            "description": skill.description,
        }
        if skill.license:
            frontmatter["license"] = skill.license
        if skill.compatibility:
            frontmatter["compatibility"] = skill.compatibility
        if skill.metadata:
            frontmatter["metadata"] = skill.metadata

        artifacts: list[RenderedArtifact] = [
            RenderedArtifact.text(
                f"{base}/SKILL.md",
                "---\n"
                + dump_yaml(frontmatter)
                + "\n---\n\n"
                + skill.skill_markdown_body(),
            )
        ]

        for rel_path, content in skill.references.items():
            artifacts.append(RenderedArtifact.text(f"{base}/references/{rel_path}", content))
        for rel_path, content in skill.scripts.items():
            artifacts.append(RenderedArtifact.text(f"{base}/scripts/{rel_path}", content))
        for rel_path, content in skill.assets.items():
            artifacts.append(RenderedArtifact(path=f"{base}/assets/{rel_path}", content=content))

        return artifacts


class ChatGPTSkillsRenderer(AgentSkillsRenderer):
    """OpenAI/ChatGPT uses the Agent Skills open standard publicly.

    We keep the package minimal and standards-first: SKILL.md + optional resources.
    """

    pass
