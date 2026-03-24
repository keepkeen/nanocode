from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
import hashlib
import json
import uuid


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolName(str, Enum):
    BASH = "bash"
    WEBSEARCH = "websearch"
    WEBFETCH = "webfetch"


@dataclass(slots=True)
class ToolContext:
    session_id: str
    user_id: str = "local-user"
    cwd: Path = field(default_factory=lambda: Path.cwd())
    tags: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class WarningItem:
    code: str
    message: str
    risk: RiskLevel = RiskLevel.MEDIUM


@dataclass(slots=True)
class ToolResult:
    ok: bool
    tool: ToolName
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[WarningItem] = field(default_factory=list)
    audit_id: str | None = None


@dataclass(slots=True)
class AuditRecord:
    audit_id: str
    timestamp: str
    session_id: str
    tool: str
    decision: str
    payload_sha256: str
    result_sha256: str
    prev_hash: str | None
    chain_hash: str
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SearchHit:
    title: str
    url: str
    snippet: str = ""
    score: float | None = None
    source: str = ""
    published_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FetchContent:
    url: str
    final_url: str
    title: str
    text: str
    content_type: str
    status_code: int
    redirects: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CommandExecution:
    argv: list[str]
    shell: bool
    cwd: str
    timeout_sec: int
    env: dict[str, str]
    requires_approval: bool
    risk: RiskLevel
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    truncated: bool = False
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


def stable_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)



def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()



def new_audit_id() -> str:
    return uuid.uuid4().hex
