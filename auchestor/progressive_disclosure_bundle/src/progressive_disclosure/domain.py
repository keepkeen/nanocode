from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping, MutableMapping, Sequence


class DisclosureLevel(str, Enum):
    ACK = "ack"
    PLAN = "plan"
    STEP = "step"
    EVIDENCE = "evidence"
    TRACE = "trace"


class DisclosureVerbosity(str, Enum):
    MINIMAL = "minimal"
    BALANCED = "balanced"
    DETAILED = "detailed"


class DisclosureAudience(str, Enum):
    END_USER = "end_user"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    OPERATOR = "operator"


class TaskRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentPhase(str, Enum):
    INTAKE = "intake"
    PLANNING = "planning"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    RECOVERY = "recovery"
    COMPLETE = "complete"


class ActionKind(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    REVIEW = "review"
    VERIFY = "verify"
    PLAN = "plan"
    SUBAGENT = "subagent"
    WAIT = "wait"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    title: str
    source_type: str
    pointer: str
    summary: str
    freshness: str | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActionRecord:
    kind: ActionKind
    description: str
    target: str | None = None
    irreversible: bool = False
    external_effect: bool = False
    user_visible: bool = True
    estimated_cost: float | None = None
    evidence_refs: Sequence[EvidenceRef] = field(default_factory=tuple)


@dataclass(slots=True)
class TaskStateSnapshot:
    task_id: str
    goal: str
    current_step: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    confidence: float = 0.7
    uncertainty_reasons: Sequence[str] = field(default_factory=tuple)
    changed_files: Sequence[str] = field(default_factory=tuple)
    running_tools: Sequence[str] = field(default_factory=tuple)
    elapsed: timedelta = timedelta(0)
    token_usage: int | None = None
    cost_estimate: float | None = None
    notes: MutableMapping[str, Any] = field(default_factory=dict)

    @property
    def progress_ratio(self) -> float | None:
        if self.progress_current is None or self.progress_total in (None, 0):
            return None
        return max(0.0, min(1.0, self.progress_current / self.progress_total))


@dataclass(frozen=True, slots=True)
class DisclosurePreferences:
    audience: DisclosureAudience = DisclosureAudience.END_USER
    verbosity: DisclosureVerbosity = DisclosureVerbosity.BALANCED
    min_interval_seconds: int = 15
    deep_trace_default: bool = False
    always_show_plan_for_medium_risk: bool = True
    always_show_evidence_before_write: bool = True
    max_evidence_items: int = 4
    max_trace_items: int = 8


@dataclass(slots=True)
class DisclosureContext:
    state: TaskStateSnapshot
    phase: AgentPhase
    risk: TaskRisk
    preferences: DisclosurePreferences = field(default_factory=DisclosurePreferences)
    current_action: ActionRecord | None = None
    plan_outline: Sequence[str] = field(default_factory=tuple)
    explicit_user_request_for_details: bool = False
    blocked_reason: str | None = None
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event: Any | None = None

    def with_event(self, event: Any) -> "DisclosureContext":
        cloned = replace(self)
        cloned.event = event
        return cloned


@dataclass(frozen=True, slots=True)
class DisclosureDecision:
    should_emit: bool
    level: DisclosureLevel | None = None
    title: str | None = None
    reasons: Sequence[str] = field(default_factory=tuple)
    sections: Sequence[str] = field(default_factory=tuple)
    include_evidence: bool = False
    include_trace: bool = False
    require_approval: bool = False
    force: bool = False


@dataclass(frozen=True, slots=True)
class DisclosureMessage:
    level: DisclosureLevel
    title: str
    summary: str
    body: str
    sections: Mapping[str, Sequence[str] | str]
    evidence: Sequence[EvidenceRef] = field(default_factory=tuple)
    trace: Sequence[str] = field(default_factory=tuple)
    require_approval: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)
