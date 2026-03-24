"""Unified agent memory and cache optimization toolkit.

This package implements a provider-agnostic memory layer for agents with:
- prefix-stable cache planning
- hierarchical memory retention
- delta compaction
- provider payload adapters for OpenAI, DeepSeek, GLM, MiniMax, Kimi, Anthropic,
  plus Claude Code style project memory export.
"""

from .models import (
    Message,
    MessageRole,
    MemoryKind,
    MemoryRecord,
    MemoryTier,
    ProviderCapability,
    ProviderRequest,
    ProviderType,
)
from .memory_store import InMemoryMemoryStore
from .compression import RuleBasedDeltaCompressor
from .cache import PrefixStableCachePlanner
from .manager import HierarchicalMemoryManager
from .claude_code_memory import ClaudeCodeProjectMemory

__all__ = [
    "Message",
    "MessageRole",
    "MemoryKind",
    "MemoryRecord",
    "MemoryTier",
    "ProviderCapability",
    "ProviderRequest",
    "ProviderType",
    "InMemoryMemoryStore",
    "RuleBasedDeltaCompressor",
    "PrefixStableCachePlanner",
    "HierarchicalMemoryManager",
    "ClaudeCodeProjectMemory",
]
