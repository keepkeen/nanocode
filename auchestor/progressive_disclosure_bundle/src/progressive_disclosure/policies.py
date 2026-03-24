from __future__ import annotations

from dataclasses import dataclass

from .abstractions import AbstractDisclosurePolicy
from .domain import (
    ActionKind,
    DisclosureAudience,
    DisclosureContext,
    DisclosureDecision,
    DisclosureLevel,
    DisclosureVerbosity,
    TaskRisk,
)
from .events import EventKind


@dataclass(slots=True)
class AdaptiveProgressiveDisclosurePolicy(AbstractDisclosurePolicy):
    """Heuristic policy informed by recent agent UX and transparency research.

    Core design principles:
    - Always keep the first visible layer short and stable.
    - Escalate before risky or irreversible actions.
    - Prefer evidence over raw trace unless the user explicitly asks for more.
    - Separate plan visibility from trace visibility.
    - Increase disclosure for low confidence, blockers, and errors.
    """

    def decide(self, context: DisclosureContext) -> DisclosureDecision:
        event = context.event
        if event is None:
            return DisclosureDecision(False)

        if event.kind == EventKind.DEEP_DIVE_REQUESTED:
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.TRACE,
                title="Deep dive into current run",
                sections=("mission", "current_action", "evidence", "trace", "next_step"),
                include_evidence=True,
                include_trace=True,
                force=True,
                reasons=("explicit_user_request",),
            )

        if event.kind == EventKind.SUMMARY_REQUESTED:
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.EVIDENCE,
                title="Condensed progress summary",
                sections=("mission", "plan", "current_action", "evidence", "next_step"),
                include_evidence=True,
                force=True,
                reasons=("explicit_summary_request",),
            )

        if event.kind == EventKind.TASK_STARTED:
            if context.risk in {TaskRisk.HIGH, TaskRisk.CRITICAL} or context.preferences.always_show_plan_for_medium_risk:
                return DisclosureDecision(
                    should_emit=True,
                    level=DisclosureLevel.PLAN,
                    title="Task received and plan forming",
                    sections=("mission", "plan", "risk", "next_step"),
                    include_evidence=False,
                    reasons=("initial_orientation",),
                )
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.ACK,
                title="Task received",
                sections=("mission", "next_step"),
                reasons=("initial_ack",),
            )

        if event.kind in {EventKind.PLAN_CREATED, EventKind.PLAN_UPDATED}:
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.PLAN,
                title="Plan updated",
                sections=("mission", "plan", "risk", "next_step"),
                include_evidence=context.risk in {TaskRisk.HIGH, TaskRisk.CRITICAL},
                reasons=("plan_change",),
            )

        if event.kind == EventKind.APPROVAL_REQUIRED:
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.EVIDENCE,
                title="Approval required before next action",
                sections=("mission", "current_action", "risk", "evidence", "next_step"),
                include_evidence=True,
                require_approval=True,
                force=True,
                reasons=("approval_gate",),
            )

        if event.kind == EventKind.ERROR:
            include_trace = (
                context.preferences.deep_trace_default
                or context.preferences.audience in {DisclosureAudience.DEVELOPER, DisclosureAudience.OPERATOR}
                or context.preferences.verbosity == DisclosureVerbosity.DETAILED
            )
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.TRACE if include_trace else DisclosureLevel.EVIDENCE,
                title="Agent hit an error and is recovering",
                sections=("mission", "current_action", "risk", "evidence", "trace", "next_step"),
                include_evidence=True,
                include_trace=include_trace,
                force=True,
                reasons=("error_recovery",),
            )

        if event.kind == EventKind.STALLED:
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.STEP,
                title="Agent is blocked",
                sections=("mission", "current_action", "risk", "next_step"),
                include_evidence=context.risk in {TaskRisk.HIGH, TaskRisk.CRITICAL},
                force=context.risk in {TaskRisk.HIGH, TaskRisk.CRITICAL},
                reasons=("stalled",),
            )

        if event.kind == EventKind.ACTION_STARTED:
            return self._for_action_started(context)

        if event.kind == EventKind.ACTION_COMPLETED:
            return self._for_action_completed(context)

        if event.kind == EventKind.TASK_COMPLETED:
            include_trace = context.preferences.audience in {DisclosureAudience.DEVELOPER, DisclosureAudience.OPERATOR}
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.EVIDENCE,
                title="Task completed",
                sections=("mission", "evidence", "trace", "next_step"),
                include_evidence=True,
                include_trace=include_trace,
                force=True,
                reasons=("completion",),
            )

        return DisclosureDecision(False)

    def _for_action_started(self, context: DisclosureContext) -> DisclosureDecision:
        action = context.current_action
        if action is None:
            return DisclosureDecision(False)

        risky_action = action.irreversible or action.external_effect or action.kind in {
            ActionKind.WRITE,
            ActionKind.EXECUTE,
            ActionKind.NETWORK,
        }
        low_confidence = context.state.confidence < 0.55

        if risky_action and context.preferences.always_show_evidence_before_write:
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.EVIDENCE if (context.risk != TaskRisk.LOW or low_confidence) else DisclosureLevel.STEP,
                title="Starting a consequential action",
                sections=("mission", "current_action", "risk", "evidence", "next_step"),
                include_evidence=True,
                require_approval=action.irreversible,
                reasons=("consequential_action",),
            )

        if low_confidence or context.risk in {TaskRisk.HIGH, TaskRisk.CRITICAL}:
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.EVIDENCE,
                title="Starting a higher-risk step",
                sections=("mission", "current_action", "risk", "evidence", "next_step"),
                include_evidence=True,
                reasons=("high_risk_step",),
            )

        return DisclosureDecision(
            should_emit=True,
            level=DisclosureLevel.STEP,
            title="Working on the next step",
            sections=("mission", "current_action", "next_step"),
            reasons=("routine_progress",),
        )

    def _for_action_completed(self, context: DisclosureContext) -> DisclosureDecision:
        action = context.current_action
        if action is None:
            return DisclosureDecision(False)

        verification_like = action.kind in {ActionKind.VERIFY, ActionKind.REVIEW}
        changed_files = len(context.state.changed_files)
        low_confidence = context.state.confidence < 0.55

        if verification_like or low_confidence or changed_files >= 3:
            return DisclosureDecision(
                should_emit=True,
                level=DisclosureLevel.EVIDENCE,
                title="Step finished with verifiable output",
                sections=("mission", "current_action", "evidence", "next_step"),
                include_evidence=True,
                reasons=("verification_material",),
            )

        return DisclosureDecision(
            should_emit=True,
            level=DisclosureLevel.STEP,
            title="Step finished",
            sections=("mission", "current_action", "next_step"),
            reasons=("step_finished",),
        )
