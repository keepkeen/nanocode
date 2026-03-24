from __future__ import annotations

from ..models import ProviderArtifact, SubAgentDefinition
from .base import BaseProviderAdapter


class DeepSeekAdapter(BaseProviderAdapter):
    provider_name = "deepseek"

    def build_artifact(self, definition: SubAgentDefinition, sample_task: str) -> ProviderArtifact:
        function_name = f"delegate_to_{definition.name.replace('-', '_')}"
        tool_definition = {
            "type": "function",
            "function": {
                "name": function_name,
                "description": definition.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Delegated task"},
                        "shared_context": {"type": "object", "description": "Optional context"},
                    },
                    "required": ["task"],
                },
            },
        }
        invocation = {
            "base_url": "https://api.deepseek.com",
            "model": definition.model_preferences.get("deepseek", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": definition.system_prompt},
                {"role": "user", "content": sample_task},
            ],
            "tools": [tool_definition],
            "response_format": {"type": "json_object"},
        }
        notes = [
            "DeepSeek exposes OpenAI-compatible chat completions plus function calling and JSON output.",
            "This adapter maps sub-agent delegation to a function tool because DeepSeek does not expose a separate named subagent config page in the surveyed docs.",
        ]
        return ProviderArtifact(self.provider_name, tool_definition, invocation, notes)
