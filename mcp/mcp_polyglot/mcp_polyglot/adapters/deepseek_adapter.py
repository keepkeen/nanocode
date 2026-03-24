from __future__ import annotations

from .openai_compat_adapter import OpenAICompatibleFunctionAdapter


class DeepSeekAdapter(OpenAICompatibleFunctionAdapter):
    provider_name = "deepseek"
    base_url = "https://api.deepseek.com"
