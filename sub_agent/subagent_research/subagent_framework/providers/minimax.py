from __future__ import annotations

from ..models import ProviderArtifact, SubAgentDefinition
from .base import BaseProviderAdapter


class MiniMaxAdapter(BaseProviderAdapter):
    provider_name = "minimax"

    def build_artifact(self, definition: SubAgentDefinition, sample_task: str) -> ProviderArtifact:
        openai_compat = {
            "base_url": "https://api.minimax.io/v1",
            "model": definition.model_preferences.get("minimax_openai", "MiniMax-M2.7"),
            "messages": [
                {"role": "system", "content": definition.system_prompt},
                {"role": "user", "content": sample_task},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": f"delegate_to_{definition.name.replace('-', '_')}",
                        "description": definition.description,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string"},
                                "reasoning_mode": {"type": "string", "enum": ["split", "inline"]},
                            },
                            "required": ["task"],
                        },
                    },
                }
            ],
            "extra_body": {"reasoning_split": True},
        }
        anthropic_compat = {
            "base_url": "https://api.minimax.io/anthropic",
            "model": definition.model_preferences.get("minimax_anthropic", "MiniMax-M2.7"),
            "messages": [{"role": "user", "content": sample_task}],
            "system": definition.system_prompt,
            "tools": [
                {
                    "name": f"delegate_to_{definition.name.replace('-', '_')}",
                    "description": definition.description,
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string"},
                            "memory_snapshot": {"type": "string"},
                        },
                        "required": ["task"],
                    },
                }
            ],
        }
        notes = [
            "MiniMax publishes both OpenAI-compatible and Anthropic-compatible APIs.",
            "For M2.7 interleaved thinking, the full response including reasoning fields should be appended back into history between tool rounds.",
        ]
        return ProviderArtifact(
            self.provider_name,
            {"openai_compatible": openai_compat, "anthropic_compatible": anthropic_compat},
            {"sample_task": sample_task},
            notes,
        )
