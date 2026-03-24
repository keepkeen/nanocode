from __future__ import annotations

from textwrap import dedent

from ..models import ProviderArtifact, SubAgentDefinition
from .base import BaseProviderAdapter


class ClaudeCodeAdapter(BaseProviderAdapter):
    provider_name = "claude_code"

    def build_artifact(self, definition: SubAgentDefinition, sample_task: str) -> ProviderArtifact:
        model_name = definition.model_preferences.get("claude_code", "sonnet")
        tool_list = ", ".join(tool.name for tool in definition.tools) or "Read, Grep, Glob"
        markdown = dedent(
            f"""\
            ---
            name: {definition.name}
            description: {definition.description}
            tools: {tool_list}
            model: {model_name}
            ---
            {definition.system_prompt.strip()}

            {definition.instructions.strip()}
            """
        ).strip()
        invocation = {
            "cli": [
                f"Use the {definition.name} subagent to handle: {sample_task}",
                f"@agent-{definition.name} {sample_task}",
                f"claude --agent {definition.name}",
            ],
            "agent_sdk": {
                "name": definition.name,
                "description": definition.description,
                "prompt": definition.system_prompt.strip() + "\n\n" + definition.instructions.strip(),
                "model": model_name,
            },
        }
        notes = [
            "Claude Code subagents are stored as Markdown files with YAML frontmatter.",
            "Claude Agent SDK can also define subagents programmatically or via filesystem-based agent files.",
        ]
        return ProviderArtifact(self.provider_name, markdown, invocation, notes)
