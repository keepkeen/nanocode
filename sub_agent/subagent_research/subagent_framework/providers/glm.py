from __future__ import annotations

from ..models import ProviderArtifact, SubAgentDefinition
from .base import BaseProviderAdapter


class GLMAdapter(BaseProviderAdapter):
    provider_name = "glm"

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
                        "memory_snapshot": {"type": "string", "description": "Compressed context"},
                    },
                    "required": ["task"],
                },
            },
        }
        invocation = {
            "endpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            "model": definition.model_preferences.get("glm", "glm-5"),
            "messages": [
                {"role": "system", "content": definition.system_prompt},
                {"role": "user", "content": sample_task},
            ],
            "tools": [tool_definition],
            "tool_choice": "auto",
            "response_format": {"type": "json_object"},
        }
        notes = [
            "GLM officially documents tool calling, JSON structured output, and MCP-based agent extensions.",
            "The adapter uses function calling for delegation and leaves MCP tools orthogonal to sub-agent routing.",
        ]
        return ProviderArtifact(self.provider_name, tool_definition, invocation, notes)
