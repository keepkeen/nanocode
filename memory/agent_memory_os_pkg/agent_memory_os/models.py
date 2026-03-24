from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import uuid

from .utils import content_address, normalize_space, sparse_embed


class ProviderType(str, Enum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    GLM = "glm"
    KIMI = "kimi"
    MINIMAX = "minimax"
    ANTHROPIC = "anthropic"
    CLAUDE_CODE = "claude_code"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    DEVELOPER = "developer"
    CACHE = "cache"


class BlockPlane(str, Enum):
    CONTROL = "control"
    EVIDENCE = "evidence"
    DERIVED = "derived"
    EXECUTION = "execution"


class BlockKind(str, Enum):
    POLICY = "policy"
    TOOL_MANIFEST = "tool_manifest"
    PREFERENCE = "preference"
    FACT = "fact"
    CONSTRAINT = "constraint"
    DECISION = "decision"
    TASK_STATE = "task_state"
    SUMMARY = "summary"
    ARTIFACT_REF = "artifact_ref"
    EPISODE = "episode"
    STYLE = "style"
    ENVIRONMENT = "environment"


@dataclass(slots=True)
class Message:
    role: MessageRole
    content: str
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def approx_tokens(self) -> int:
        return max(1, len(self.content or "") // 4)

    def to_openai_dict(self) -> Dict[str, Any]:
        role = self.metadata.get("provider_role") or self.role.value
        payload: Dict[str, Any] = {"role": role, "content": self.content}
        if self.name:
            payload["name"] = self.name
        if self.metadata.get("tool_call_id"):
            payload["tool_call_id"] = self.metadata["tool_call_id"]
        return payload


@dataclass(slots=True)
class EventRecord:
    namespace: str
    role: MessageRole
    content: str
    source: str = "conversation"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def approx_tokens(self) -> int:
        return max(1, len(self.content or "") // 4)


@dataclass(slots=True)
class MemoryBlock:
    namespace: str
    plane: BlockPlane
    kind: BlockKind
    text: str
    salience: float = 0.5
    stability: float = 0.5
    confidence: float = 0.7
    source_event_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    supersedes: Optional[str] = None
    active: bool = True
    block_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def address(self) -> str:
        return content_address(
            {
                "plane": self.plane.value,
                "kind": self.kind.value,
                "text": normalize_space(self.text),
                "tags": sorted(self.tags),
                "references": sorted(self.references),
                "supersedes": self.supersedes,
            }
        )

    def approx_tokens(self) -> int:
        return max(1, len(self.text or "") // 4)

    def embedding(self) -> Dict[str, float]:
        return sparse_embed(self.text + " " + " ".join(self.tags))


@dataclass(slots=True)
class RetrievalHit:
    block: MemoryBlock
    score: float
    channel_scores: Dict[str, float] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextZone:
    name: str
    messages: List[Message]
    stable: bool
    notes: str = ""

    def approx_tokens(self) -> int:
        return sum(m.approx_tokens() for m in self.messages)


@dataclass(slots=True)
class ContextAssembly:
    zones: List[ContextZone]
    provider_hints: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def merged_messages(self) -> List[Message]:
        out: List[Message] = []
        for zone in self.zones:
            out.extend(zone.messages)
        return out

    def stable_prefix_messages(self) -> List[Message]:
        out: List[Message] = []
        for zone in self.zones:
            if not zone.stable:
                break
            out.extend(zone.messages)
        return out


@dataclass(slots=True)
class ToolSchema:
    name: str
    description: str
    parameters_json_schema: Dict[str, Any]

    def stable_hash(self) -> str:
        return content_address(
            {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_json_schema,
            }
        )[:16]


@dataclass(slots=True)
class ProviderRequest:
    provider: ProviderType
    endpoint_style: str
    path: str
    payload: Dict[str, Any]
    headers: Dict[str, str] = field(default_factory=dict)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def pretty_json(self) -> str:
        return json.dumps(
            {
                "provider": self.provider.value,
                "endpoint_style": self.endpoint_style,
                "path": self.path,
                "headers": self.headers,
                "payload": self.payload,
                "diagnostics": self.diagnostics,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
