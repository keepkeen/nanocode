from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from ..models import ProviderType
from .anthropic import AnthropicMessagesAdapter
from .compatible import DeepSeekAdapter, GLMAdapter, KimiAdapter, MiniMaxAdapter
from .openai import OpenAIChatAdapter, OpenAIResponsesAdapter


@dataclass(slots=True)
class ProviderCapability:
    provider: ProviderType
    cache_mode: str
    compaction_mode: str
    notes: str


PROVIDER_CAPABILITIES: Dict[str, ProviderCapability] = {
    "openai_responses": ProviderCapability(ProviderType.OPENAI, "automatic prefix cache + prompt_cache_key", "server-side compaction", "Responses API also supports previous_response_id / conversation state."),
    "openai_chat": ProviderCapability(ProviderType.OPENAI, "automatic prefix cache + prompt_cache_key", "none", "Use manual memory layer + stable prefix layout."),
    "anthropic": ProviderCapability(ProviderType.ANTHROPIC, "top-level automatic cache_control or explicit breakpoints", "context_management compact_20260112", "Prefer top-level automatic caching for long multi-turn sessions."),
    "deepseek": ProviderCapability(ProviderType.DEEPSEEK, "implicit prefix disk cache", "none", "Stateless API; keep stable prefix byte-identical."),
    "glm": ProviderCapability(ProviderType.GLM, "implicit context cache", "none", "Observe usage.prompt_tokens_details.cached_tokens."),
    "kimi": ProviderCapability(ProviderType.KIMI, "context cache objects referenced via role=cache", "none", "Chat itself is stateless; official memory tool also exists."),
    "minimax": ProviderCapability(ProviderType.MINIMAX, "automatic passive cache", "none", "OpenAI-compatible chat or Anthropic-compatible messages are both supported."),
    "minimax_anthropic": ProviderCapability(ProviderType.MINIMAX, "explicit cache_control via Anthropic-compatible mode", "none", "Useful when you want block-level cache semantics."),
}


def build_default_adapters() -> Dict[str, object]:
    return {
        "openai_responses": OpenAIResponsesAdapter(),
        "openai_chat": OpenAIChatAdapter(),
        "anthropic": AnthropicMessagesAdapter(),
        "deepseek": DeepSeekAdapter(),
        "glm": GLMAdapter(),
        "kimi": KimiAdapter(),
        "minimax": MiniMaxAdapter(anthropic_compatible=False),
        "minimax_anthropic": MiniMaxAdapter(anthropic_compatible=True),
    }
