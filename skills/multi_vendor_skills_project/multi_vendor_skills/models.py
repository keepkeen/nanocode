from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable
import re


class Provider(str, Enum):
    CHATGPT = "chatgpt"
    CLAUDE_CODE = "claude-code"
    CLAUDE_SUBAGENT = "claude-subagent"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    MINIMAX_OPENAI = "minimax-openai"
    MINIMAX_ANTHROPIC = "minimax-anthropic"
    KIMI = "kimi"


ToolExecutor = Callable[[dict[str, Any]], Any]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    executor: ToolExecutor | None = None
    strict: bool = False

    def validate(self) -> None:
        if not self.name or not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", self.name):
            raise ValueError(
                f"Invalid tool name {self.name!r}. Expected 1-64 chars of letters, numbers, underscore, or hyphen."
            )
        if self.parameters.get("type") != "object":
            raise ValueError(f"Tool {self.name!r} must use a JSON schema object as parameters.")


@dataclass(slots=True)
class InvocationExample:
    title: str
    prompt: str


@dataclass(slots=True)
class RenderedArtifact:
    path: str
    content: bytes

    @classmethod
    def text(cls, path: str, text: str) -> "RenderedArtifact":
        return cls(path=path, content=text.encode("utf-8"))

    def write_into(self, root: Path) -> Path:
        target = root / self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.content)
        return target


@dataclass(slots=True)
class SkillDefinition:
    name: str
    title: str
    description: str
    instructions: str
    tools: list[ToolSpec] = field(default_factory=list)
    examples: list[InvocationExample] = field(default_factory=list)
    references: dict[str, str] = field(default_factory=dict)
    scripts: dict[str, str] = field(default_factory=dict)
    assets: dict[str, bytes] = field(default_factory=dict)
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.name):
            raise ValueError(
                f"Invalid skill name {self.name!r}. Use lowercase letters, numbers, and single hyphens only."
            )
        if len(self.name) > 64:
            raise ValueError("Skill name must be at most 64 characters.")
        if not self.description.strip():
            raise ValueError("Skill description must not be empty.")
        if len(self.description) > 1024:
            raise ValueError("Skill description must be at most 1024 characters.")
        for tool in self.tools:
            tool.validate()

    def skill_markdown_body(self) -> str:
        sections: list[str] = [f"# {self.title}", self.instructions.strip()]
        if self.examples:
            sections.append("## Examples")
            for example in self.examples:
                sections.append(f"- {example.title}: `{example.prompt}`")
        return "\n\n".join(sections).strip() + "\n"
