from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import hashlib
import json
import uuid


class ProviderType(str, Enum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    MINIMAX = "minimax"
    KIMI = "kimi"
    ANTHROPIC = "anthropic"
    CLAUDE_CODE = "claude_code"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    DEVELOPER = "developer"


class MemoryTier(str, Enum):
    INSTRUCTION = "instruction"
    PINNED = "pinned"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    WORKING = "working"
    COMPACTED = "compacted"


class MemoryKind(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    TASK = "task"
    CONSTRAINT = "constraint"
    DECISION = "decision"
    ARTIFACT = "artifact"
    ENVIRONMENT = "environment"
    SUMMARY = "summary"


@dataclass(slots=True)
class Message:
    role: MessageRole
    content: str
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def approx_tokens(self) -> int:
        text = self.content or ""
        return max(1, len(text) // 4)

    def to_openai_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.name:
            payload["name"] = self.name
        if self.metadata.get("tool_call_id"):
            payload["tool_call_id"] = self.metadata["tool_call_id"]
        return payload

    def to_anthropic_block(self) -> Dict[str, Any]:
        return {
            "role": "assistant" if self.role == MessageRole.ASSISTANT else "user",
            "content": [{"type": "text", "text": self.content}],
        }


@dataclass(slots=True)
class MemoryRecord:
    text: str
    kind: MemoryKind
    tier: MemoryTier
    salience: float = 0.5
    durability: float = 0.5
    namespace: str = "default"
    source_message_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    privacy_class: str = "internal"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: Optional[datetime] = None
    memory_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    tombstoned: bool = False

    def touch(self) -> None:
        self.last_accessed_at = datetime.now(timezone.utc)

    def approx_tokens(self) -> int:
        return max(1, len(self.text) // 4)

    def age_hours(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        return max(0.0, (now - self.created_at).total_seconds() / 3600.0)

    def retrieval_score(self, query: str, now: Optional[datetime] = None) -> float:
        query_terms = set(_normalize_terms(query))
        mem_terms = set(_normalize_terms(self.text + " " + " ".join(self.tags)))
        overlap = len(query_terms & mem_terms) / max(1, len(query_terms))
        age_penalty = 1.0 / (1.0 + self.age_hours(now) / 72.0)
        tier_bonus = {
            MemoryTier.INSTRUCTION: 1.8,
            MemoryTier.PINNED: 1.6,
            MemoryTier.SEMANTIC: 1.3,
            MemoryTier.EPISODIC: 1.1,
            MemoryTier.COMPACTED: 1.0,
            MemoryTier.WORKING: 0.8,
        }[self.tier]
        return (0.4 * self.salience + 0.3 * self.durability + 0.3 * overlap) * age_penalty * tier_bonus


@dataclass(slots=True)
class CompressionResult:
    summary: str
    compacted_messages: List[Message]
    extracted_memories: List[MemoryRecord]
    dropped_message_ids: List[str]
    stats: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CachePlan:
    stable_prefix: List[Message]
    memory_injection: List[Message]
    dynamic_tail: List[Message]
    provider_hints: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def merged_messages(self) -> List[Message]:
        return [*self.stable_prefix, *self.memory_injection, *self.dynamic_tail]


@dataclass(slots=True)
class ProviderCapability:
    provider: ProviderType
    message_format: str
    automatic_prefix_cache: bool
    explicit_cache_control: bool
    server_side_compaction: bool
    built_in_persistent_memory: bool
    notes: str


@dataclass(slots=True)
class ProviderRequest:
    provider: ProviderType
    endpoint_style: str
    payload: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def pretty_json(self) -> str:
        return json.dumps(
            {
                "provider": self.provider.value,
                "endpoint_style": self.endpoint_style,
                "headers": self.headers,
                "payload": self.payload,
                "diagnostics": self.diagnostics,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )


@dataclass(slots=True)
class ToolSchema:
    name: str
    description: str
    parameters_json_schema: Dict[str, Any]

    def stable_hash(self) -> str:
        canonical = json.dumps(
            {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_json_schema,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class MemoryWriteDecision:
    should_store: bool
    tier: MemoryTier
    salience: float
    durability: float
    reason: str


def canonical_message_fingerprint(messages: List[Message]) -> str:
    normalized = [
        {
            "role": m.role.value,
            "name": m.name,
            "content": m.content,
            "metadata": {k: m.metadata[k] for k in sorted(m.metadata)},
        }
        for m in messages
    ]
    data = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _normalize_terms(text: str) -> List[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return [term for term in cleaned.split() if term]
