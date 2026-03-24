from __future__ import annotations

from datetime import timedelta

from progressive_disclosure import (
    ActionKind,
    ActionRecord,
    AgentEvent,
    AgentPhase,
    DisclosureAudience,
    DisclosureContext,
    DisclosureLevel,
    DisclosurePreferences,
    DisclosureVerbosity,
    EvidenceRef,
    EventKind,
    ProgressiveDisclosureEngine,
    ProgressiveDisclosureManager,
    TaskRisk,
    TaskStateSnapshot,
)


def make_context(*, phase: AgentPhase, risk: TaskRisk, confidence: float = 0.8, action: ActionRecord | None = None):
    return DisclosureContext(
        state=TaskStateSnapshot(
            task_id="t1",
            goal="Update billing retry strategy",
            current_step="working",
            progress_current=1,
            progress_total=3,
            confidence=confidence,
            elapsed=timedelta(seconds=30),
        ),
        phase=phase,
        risk=risk,
        current_action=action,
        plan_outline=("Inspect current strategy", "Patch backoff config", "Verify tests"),
        preferences=DisclosurePreferences(
            audience=DisclosureAudience.DEVELOPER,
            verbosity=DisclosureVerbosity.DETAILED,
            min_interval_seconds=0,
        ),
    )


def test_high_risk_task_start_emits_plan():
    engine = ProgressiveDisclosureEngine()
    msg = engine.process(
        AgentEvent(kind=EventKind.TASK_STARTED),
        make_context(phase=AgentPhase.INTAKE, risk=TaskRisk.HIGH),
    )
    assert msg is not None
    assert msg.level == DisclosureLevel.PLAN
    assert "mission" in msg.sections


def test_approval_required_escalates_to_evidence():
    engine = ProgressiveDisclosureEngine()
    action = ActionRecord(
        kind=ActionKind.EXECUTE,
        description="Run migration against staging",
        target="alembic upgrade head",
        irreversible=True,
        external_effect=True,
        evidence_refs=(
            EvidenceRef(
                title="Migration doc",
                source_type="repo-doc",
                pointer="docs/db/migrations.md",
                summary="Staging migration touches customer billing tables.",
            ),
        ),
    )
    msg = engine.process(
        AgentEvent(kind=EventKind.APPROVAL_REQUIRED),
        make_context(phase=AgentPhase.EXECUTION, risk=TaskRisk.HIGH, action=action),
    )
    assert msg is not None
    assert msg.level == DisclosureLevel.EVIDENCE
    assert msg.require_approval is True
    assert msg.evidence


def test_error_for_developer_includes_trace_when_requested_by_preferences():
    engine = ProgressiveDisclosureEngine()
    engine.trace_provider = engine.trace_provider.__class__(traces_by_event={str(EventKind.ERROR): ("trace line 1", "trace line 2")})
    prefs = DisclosurePreferences(
        audience=DisclosureAudience.OPERATOR,
        verbosity=DisclosureVerbosity.DETAILED,
        min_interval_seconds=0,
        deep_trace_default=True,
    )
    context = DisclosureContext(
        state=TaskStateSnapshot(task_id="t1", goal="Recover run", current_step="retrying", confidence=0.4),
        phase=AgentPhase.RECOVERY,
        risk=TaskRisk.HIGH,
        preferences=prefs,
        current_action=ActionRecord(kind=ActionKind.VERIFY, description="Inspect failure"),
        plan_outline=("reproduce", "patch", "rerun"),
    )
    msg = engine.process(AgentEvent(kind=EventKind.ERROR), context)
    assert msg is not None
    assert msg.level == DisclosureLevel.TRACE
    assert len(msg.trace) == 2


def test_manager_publishes_messages_to_sink():
    manager = ProgressiveDisclosureManager()
    msg = manager.handle_event(
        AgentEvent(kind=EventKind.TASK_COMPLETED),
        make_context(phase=AgentPhase.COMPLETE, risk=TaskRisk.MEDIUM),
    )
    assert msg is not None
    assert len(manager.sink.items) == 1


def test_novelty_gate_suppresses_duplicate_non_critical_messages():
    engine = ProgressiveDisclosureEngine()
    context = make_context(
        phase=AgentPhase.EXECUTION,
        risk=TaskRisk.LOW,
        action=ActionRecord(kind=ActionKind.READ, description="Read config file"),
    )
    first = engine.process(AgentEvent(kind=EventKind.ACTION_STARTED), context)
    second = engine.process(AgentEvent(kind=EventKind.ACTION_STARTED), context)
    assert first is not None
    assert second is None
