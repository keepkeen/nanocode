from __future__ import annotations

from ..models import ProviderArtifact, SubAgentDefinition
from .base import BaseProviderAdapter


class KimiAdapter(BaseProviderAdapter):
    provider_name = "kimi"

    def build_artifact(self, definition: SubAgentDefinition, sample_task: str) -> ProviderArtifact:
        tool_definition = {
            "type": "function",
            "function": {
                "name": f"delegate_to_{definition.name.replace('-', '_')}",
                "description": definition.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Delegated task"},
                        "language": {"type": "string", "description": "Preferred output language"},
                    },
                    "required": ["task"],
                },
            },
        }
        invocation = {
            "base_url": "https://api.moonshot.cn/v1",
            "model": definition.model_preferences.get("kimi", "kimi-k2.5"),
            "messages": [
                {"role": "system", "content": definition.system_prompt},
                {"role": "user", "content": sample_task},
            ],
            "tools": [tool_definition],
            "official_formula_examples": [
                "moonshot/web-search:latest",
                "moonshot/rethink:latest",
                "moonshot/code_runner:latest",
            ],
        }
        notes = [
            "Kimi supports generic function tools and also official Formula tools.",
            "Kimi CLI additionally supports ACP for agent client integration and MCP config files for external tools.",
        ]
        return ProviderArtifact(self.provider_name, tool_definition, invocation, notes)
