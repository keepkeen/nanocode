from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class EventKind(str, Enum):
    TASK_STARTED = "task_started"
    PLAN_CREATED = "plan_created"
    PLAN_UPDATED = "plan_updated"
    ACTION_STARTED = "action_started"
    ACTION_COMPLETED = "action_completed"
    APPROVAL_REQUIRED = "approval_required"
    STALLED = "stalled"
    ERROR = "error"
    SUMMARY_REQUESTED = "summary_requested"
    DEEP_DIVE_REQUESTED = "deep_dive_requested"
    TASK_COMPLETED = "task_completed"


@dataclass(frozen=True, slots=True)
class AgentEvent:
    kind: EventKind
    message: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def important(self) -> bool:
        return self.kind in {
            EventKind.APPROVAL_REQUIRED,
            EventKind.ERROR,
            EventKind.TASK_COMPLETED,
            EventKind.DEEP_DIVE_REQUESTED,
            EventKind.SUMMARY_REQUESTED,
        }
