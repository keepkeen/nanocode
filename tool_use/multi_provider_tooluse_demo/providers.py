from __future__ import annotations

from .adapters.anthropic_messages import AnthropicMessagesAdapter
from .adapters.openai_chat import DeepSeekAdapter, GLMAdapter, KimiAdapter, MiniMaxOpenAIAdapter
from .adapters.openai_responses import OpenAIResponsesAdapter


def make_openai_provider(model: str = "gpt-5.4") -> OpenAIResponsesAdapter:
    return OpenAIResponsesAdapter(model=model)


def make_deepseek_provider(model: str = "deepseek-chat") -> DeepSeekAdapter:
    return DeepSeekAdapter(model=model)


def make_glm_provider(model: str = "glm-5") -> GLMAdapter:
    return GLMAdapter(model=model)


def make_minimax_provider(model: str = "MiniMax-M2.7") -> MiniMaxOpenAIAdapter:
    return MiniMaxOpenAIAdapter(model=model)


def make_kimi_provider(model: str = "kimi-k2.5") -> KimiAdapter:
    return KimiAdapter(model=model)


def make_claude_provider(model: str = "claude-sonnet-4.6") -> AnthropicMessagesAdapter:
    return AnthropicMessagesAdapter(model=model)
