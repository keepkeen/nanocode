from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .abstractions import AbstractNoveltyGate
from .domain import DisclosureContext, DisclosureDecision, DisclosureMessage, DisclosureLevel


@dataclass(slots=True)
class _GateState:
    last_emitted_at: datetime | None = None
    last_fingerprint: str | None = None


class TimeAndNoveltyGate(AbstractNoveltyGate):
    """Avoids repeated or overly frequent disclosures while letting critical events through."""

    def __init__(self) -> None:
        self._state = _GateState()

    def _fingerprint(self, context: DisclosureContext, decision: DisclosureDecision) -> str:
        event_kind = getattr(getattr(context, 'event', None), 'kind', None)
        action = context.current_action.description if context.current_action else ""
        step = context.state.current_step or ""
        return "|".join([
            str(event_kind),
            str(decision.level),
            step,
            action,
            decision.title or "",
        ])

    def should_emit(self, context: DisclosureContext, decision: DisclosureDecision) -> bool:
        if decision.force:
            return True
        if decision.level in {DisclosureLevel.TRACE, DisclosureLevel.EVIDENCE} and decision.require_approval:
            return True
        event = context.event
        if getattr(event, 'important', False):
            return True

        fingerprint = self._fingerprint(context, decision)
        if self._state.last_fingerprint == fingerprint:
            return False

        if self._state.last_emitted_at is None:
            return True

        min_interval = timedelta(seconds=context.preferences.min_interval_seconds)
        return (context.now - self._state.last_emitted_at) >= min_interval

    def record(self, context: DisclosureContext, message: DisclosureMessage) -> None:
        self._state.last_emitted_at = context.now
        self._state.last_fingerprint = "|".join([
            str(getattr(getattr(context, 'event', None), 'kind', None)),
            str(message.level),
            context.state.current_step or "",
            context.current_action.description if context.current_action else "",
            message.title,
        ])
