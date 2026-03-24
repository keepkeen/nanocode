from __future__ import annotations

from ..models import ProviderArtifact, SubAgentDefinition
from .base import BaseProviderAdapter


class OpenAIChatGPTAdapter(BaseProviderAdapter):
    provider_name = "openai_chatgpt"

    def build_artifact(self, definition: SubAgentDefinition, sample_task: str) -> ProviderArtifact:
        agent_definition = {
            "name": definition.name,
            "instructions": definition.system_prompt.strip() + "\n\n" + definition.instructions.strip(),
            "handoff_description": definition.description,
            "model": definition.model_preferences.get("openai", "gpt-5"),
            "tools": [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
                for tool in definition.tools
            ],
        }
        invocation = {
            "sdk": "openai-agents-python",
            "example": {
                "triage_agent": {
                    "name": "Triage Agent",
                    "handoffs": [definition.name],
                },
                "sample_input": sample_task,
            },
            "responses_api_payload": {
                "model": definition.model_preferences.get("openai_responses", "gpt-5"),
                "input": sample_task,
                "text": {"format": {"type": "json_object"}},
                "tools": [
                    {
                        "type": "function",
                        "name": f"delegate_to_{definition.name.replace('-', '_')}",
                        "description": definition.description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string", "description": "Delegated task"}
                            },
                            "required": ["task"],
                        },
                    }
                ],
                "tool_choice": "auto",
            },
        }
        notes = [
            "OpenAI Agents SDK uses handoffs between specialized agents.",
            "Responses API can represent sub-agent delegation as a function tool for provider-agnostic orchestration.",
        ]
        return ProviderArtifact(self.provider_name, agent_definition, invocation, notes)
