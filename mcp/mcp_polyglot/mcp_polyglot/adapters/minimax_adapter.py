from __future__ import annotations

from .openai_compat_adapter import OpenAICompatibleFunctionAdapter


class MiniMaxFunctionAdapter(OpenAICompatibleFunctionAdapter):
    provider_name = "minimax"
    base_url = "https://api.minimax.chat"

    def deployment_hint(self) -> dict:
        return {
            "recommended_vllm_flags": [
                "--enable-auto-tool-choice",
                "--tool-call-parser",
                "minimax",
            ]
        }
