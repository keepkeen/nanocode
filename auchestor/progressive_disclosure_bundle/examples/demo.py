from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from progressive_disclosure import (
    ActionKind,
    ActionRecord,
    AgentEvent,
    AgentPhase,
    DisclosureAudience,
    DisclosureContext,
    DisclosurePreferences,
    DisclosureVerbosity,
    EvidenceRef,
    EventKind,
    ProgressiveDisclosureManager,
    StdoutSink,
    TaskRisk,
    TaskStateSnapshot,
)


def make_context(
    *,
    phase: AgentPhase,
    step: str,
    confidence: float,
    risk: TaskRisk,
    action: ActionRecord | None = None,
    changed_files: tuple[str, ...] = (),
    uncertainty: tuple[str, ...] = (),
    plan_outline: tuple[str, ...] = (),
):
    return DisclosureContext(
        state=TaskStateSnapshot(
            task_id="demo-1",
            goal="Refactor the authentication flow and verify login + logout.",
            current_step=step,
            progress_current=1,
            progress_total=4,
            confidence=confidence,
            changed_files=changed_files,
            uncertainty_reasons=uncertainty,
            elapsed=timedelta(minutes=12),
            token_usage=18420,
        ),
        phase=phase,
        risk=risk,
        preferences=DisclosurePreferences(
            audience=DisclosureAudience.DEVELOPER,
            verbosity=DisclosureVerbosity.DETAILED,
            min_interval_seconds=0,
            deep_trace_default=False,
        ),
        current_action=action,
        plan_outline=plan_outline,
    )


def main() -> None:
    sink = StdoutSink()
    manager = ProgressiveDisclosureManager(sink=sink)

    plan = (
        "Map auth entrypoints and middleware.",
        "Patch session refresh logic.",
        "Run login/logout verification.",
        "Summarize changed files and remaining risk.",
    )

    manager.handle_event(
        AgentEvent(kind=EventKind.TASK_STARTED, message="New refactor task"),
        make_context(phase=AgentPhase.INTAKE, step="scoping task", confidence=0.82, risk=TaskRisk.HIGH, plan_outline=plan),
    )

    manager.handle_event(
        AgentEvent(kind=EventKind.PLAN_CREATED, message="Plan created"),
        make_context(phase=AgentPhase.PLANNING, step="drafting execution plan", confidence=0.79, risk=TaskRisk.HIGH, plan_outline=plan),
    )

    risky_action = ActionRecord(
        kind=ActionKind.WRITE,
        description="Patch session refresh logic in auth service",
        target="src/auth/service.py",
        irreversible=False,
        external_effect=False,
        evidence_refs=(
            EvidenceRef(
                title="Auth architecture doc",
                source_type="repo-doc",
                pointer="docs/auth/architecture.md",
                summary="Session refresh should remain idempotent and preserve logout invariants.",
            ),
        ),
    )

    manager.handle_event(
        AgentEvent(kind=EventKind.ACTION_STARTED, message="Starting edit"),
        make_context(
            phase=AgentPhase.EXECUTION,
            step="editing refresh logic",
            confidence=0.58,
            risk=TaskRisk.HIGH,
            action=risky_action,
            uncertainty=("refresh edge-case on expired session not yet verified",),
            plan_outline=plan,
        ),
    )

    approval_action = ActionRecord(
        kind=ActionKind.EXECUTE,
        description="Run integration tests touching database fixtures",
        target="pytest tests/integration/test_auth_flow.py",
        irreversible=True,
        external_effect=True,
        evidence_refs=(
            EvidenceRef(
                title="Test scope",
                source_type="test",
                pointer="tests/integration/test_auth_flow.py",
                summary="Touches login, refresh, logout, and session invalidation paths.",
            ),
        ),
    )

    manager.handle_event(
        AgentEvent(kind=EventKind.APPROVAL_REQUIRED, message="Need approval before integration tests"),
        make_context(
            phase=AgentPhase.VERIFICATION,
            step="preparing integration verification",
            confidence=0.72,
            risk=TaskRisk.HIGH,
            action=approval_action,
            changed_files=("src/auth/service.py", "src/auth/routes.py", "tests/integration/test_auth_flow.py"),
            plan_outline=plan,
        ),
    )

    error_action = ActionRecord(
        kind=ActionKind.VERIFY,
        description="Analyze failing logout test",
        target="tests/integration/test_auth_flow.py::test_logout_clears_session",
        evidence_refs=(
            EvidenceRef(
                title="Pytest output",
                source_type="terminal",
                pointer="terminal://pytest-auth",
                summary="Logout leaves stale session cookie in one branch.",
            ),
        ),
    )

    manager.engine.trace_provider = manager.engine.trace_provider.__class__(
        traces_by_event={
            str(EventKind.ERROR): (
                "pytest -q tests/integration/test_auth_flow.py failed on test_logout_clears_session",
                "cookie invalidation path still references old refresh token helper",
                "recommended recovery: patch helper, rerun focused test, then rerun suite",
            )
        }
    )

    manager.handle_event(
        AgentEvent(kind=EventKind.ERROR, message="Focused test failed"),
        make_context(
            phase=AgentPhase.RECOVERY,
            step="debugging logout regression",
            confidence=0.44,
            risk=TaskRisk.HIGH,
            action=error_action,
            changed_files=("src/auth/service.py", "src/auth/helpers.py"),
            uncertainty=("stale helper may be called from both REST and websocket paths",),
            plan_outline=plan,
        ),
    )

    manager.handle_event(
        AgentEvent(kind=EventKind.TASK_COMPLETED, message="Auth flow completed"),
        make_context(
            phase=AgentPhase.COMPLETE,
            step="final summary",
            confidence=0.88,
            risk=TaskRisk.HIGH,
            changed_files=("src/auth/service.py", "src/auth/routes.py", "tests/integration/test_auth_flow.py"),
            plan_outline=plan,
        ),
    )


if __name__ == "__main__":
    main()
