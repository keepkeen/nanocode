from __future__ import annotations

import sqlite3

from nanocli.models import RunStatus, TraceKind
from nanocli.storage import LocalStateStore


def test_store_round_trip(tmp_path):
    store = LocalStateStore(tmp_path / "state.db", tmp_path / "artifacts")
    run = store.create_run(objective="Test objective", profile="openai", cwd=tmp_path)
    artifact = store.save_artifact(run.run_id, "request", {"Authorization": "secret", "ok": True})
    trace = store.append_trace(
        run.run_id,
        kind=TraceKind.PROVIDER_REQUEST,
        message="compiled request",
        payload={"Authorization": "secret"},
        artifact_path=artifact,
    )
    updated = store.update_run(run.run_id, status=RunStatus.COMPILED, phase="complete", summary="done")
    traces = store.list_traces(run.run_id)

    assert trace.trace_id >= 1
    assert updated.status == RunStatus.COMPILED
    assert updated.summary == "done"
    assert len(traces) == 1
    assert traces[0].payload["Authorization"] == "***REDACTED***"
    assert "***REDACTED***" in store.load_artifact(artifact)


def test_store_migrates_existing_runs_table(tmp_path):
    db_path = tmp_path / "state.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            objective TEXT NOT NULL,
            profile TEXT NOT NULL,
            cwd TEXT NOT NULL,
            status TEXT NOT NULL,
            phase TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            error TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    store = LocalStateStore(db_path, tmp_path / "artifacts")
    run = store.create_run(objective="migrate", profile="openai", cwd=tmp_path)

    assert run.run_id
