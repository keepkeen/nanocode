from __future__ import annotations

from typing import Dict

from ..models import ProviderCapability, ProviderType
from .anthropic_adapter import AnthropicAdapter
from .deepseek_adapter import DeepSeekAdapter
from .glm_adapter import GLMAdapter
from .kimi_adapter import KimiAdapter
from .minimax_adapter import MiniMaxAdapter
from .openai_adapter import OpenAIAdapter


PROVIDER_CAPABILITIES: Dict[str, ProviderCapability] = {
    "openai": ProviderCapability(
        provider=ProviderType.OPENAI,
        message_format="Responses API or Chat Completions",
        automatic_prefix_cache=True,
        explicit_cache_control=True,
        server_side_compaction=True,
        built_in_persistent_memory=False,
        notes="API offers prompt caching, previous_response_id / conversation state, and server-side compaction.",
    ),
    "deepseek": ProviderCapability(
        provider=ProviderType.DEEPSEEK,
        message_format="OpenAI-compatible chat.completions messages",
        automatic_prefix_cache=True,
        explicit_cache_control=False,
        server_side_compaction=False,
        built_in_persistent_memory=False,
        notes="Disk cache is implicit and prefix-only; client must manage multi-turn history.",
    ),
    "glm": ProviderCapability(
        provider=ProviderType.GLM,
        message_format="OpenAI-compatible chat.completions messages",
        automatic_prefix_cache=True,
        explicit_cache_control=False,
        server_side_compaction=False,
        built_in_persistent_memory=False,
        notes="Implicit context caching across repeated or highly similar context.",
    ),
    "minimax": ProviderCapability(
        provider=ProviderType.MINIMAX,
        message_format="Native text generation messages or Anthropic-compatible messages",
        automatic_prefix_cache=True,
        explicit_cache_control=True,
        server_side_compaction=False,
        built_in_persistent_memory=False,
        notes="Native API supports automatic caching; Anthropic-compatible API supports cache_control breakpoints.",
    ),
    "kimi": ProviderCapability(
        provider=ProviderType.KIMI,
        message_format="OpenAI-compatible chat.completions messages",
        automatic_prefix_cache=False,
        explicit_cache_control=True,
        server_side_compaction=False,
        built_in_persistent_memory=False,
        notes="Context caching is explicit; core chat API is stateless and OpenAI-compatible.",
    ),
    "anthropic": ProviderCapability(
        provider=ProviderType.ANTHROPIC,
        message_format="Messages API with system field and content blocks",
        automatic_prefix_cache=True,
        explicit_cache_control=True,
        server_side_compaction=True,
        built_in_persistent_memory=False,
        notes="Prompt caching supports cache_control and compaction supports server-side summary blocks.",
    ),
    "claude_code": ProviderCapability(
        provider=ProviderType.CLAUDE_CODE,
        message_format="Project memory files (CLAUDE.md, MEMORY.md)",
        automatic_prefix_cache=False,
        explicit_cache_control=False,
        server_side_compaction=False,
        built_in_persistent_memory=True,
        notes="Project memory is file-backed; every session starts fresh, but CLAUDE.md and auto memory are loaded.",
    ),
}


def build_default_adapters() -> Dict[str, object]:
    return {
        "openai": OpenAIAdapter(),
        "deepseek": DeepSeekAdapter(),
        "glm": GLMAdapter(),
        "minimax": MiniMaxAdapter(),
        "kimi": KimiAdapter(),
        "anthropic": AnthropicAdapter(),
    }
