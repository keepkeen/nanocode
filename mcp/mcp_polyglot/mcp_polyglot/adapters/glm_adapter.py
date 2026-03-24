from __future__ import annotations

from .openai_compat_adapter import OpenAICompatibleFunctionAdapter


class GLMAdapter(OpenAICompatibleFunctionAdapter):
    provider_name = "glm"
    base_url = "https://open.bigmodel.cn/api/paas/v4"
