from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json
import sqlite3
import threading
import uuid

from .models import RunStatus, RunSummary, SessionMessageRecord, SessionSummary, TraceKind, TraceRecord, utc_now


SENSITIVE_KEYS = {"authorization", "x-api-key", "api_key", "api-key"}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in SENSITIVE_KEYS:
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


class _LockedCursor:
    def __init__(self, cursor: sqlite3.Cursor, lock: threading.RLock) -> None:
        self._cursor = cursor
        self._lock = lock

    def fetchone(self) -> sqlite3.Row | None:
        with self._lock:
            return self._cursor.fetchone()

    def fetchall(self) -> list[sqlite3.Row]:
        with self._lock:
            return self._cursor.fetchall()

    def fetchmany(self, size: int | None = None) -> list[sqlite3.Row]:
        with self._lock:
            if size is None:
                return self._cursor.fetchmany()
            return self._cursor.fetchmany(size)

    @property
    def lastrowid(self) -> int | None:
        with self._lock:
            return self._cursor.lastrowid

    @property
    def rowcount(self) -> int:
        with self._lock:
            return self._cursor.rowcount

    def __iter__(self):
        with self._lock:
            rows = self._cursor.fetchall()
        return iter(rows)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class _LockedConnection:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    @property
    def row_factory(self) -> Any:
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._conn.row_factory = value

    def execute(self, *args: Any, **kwargs: Any) -> _LockedCursor:
        with self._lock:
            cursor = self._conn.execute(*args, **kwargs)
        return _LockedCursor(cursor, self._lock)

    def executemany(self, *args: Any, **kwargs: Any) -> _LockedCursor:
        with self._lock:
            cursor = self._conn.executemany(*args, **kwargs)
        return _LockedCursor(cursor, self._lock)

    def executescript(self, *args: Any, **kwargs: Any) -> _LockedCursor:
        with self._lock:
            cursor = self._conn.executescript(*args, **kwargs)
        return _LockedCursor(cursor, self._lock)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def cursor(self, *args: Any, **kwargs: Any) -> _LockedCursor:
        with self._lock:
            cursor = self._conn.cursor(*args, **kwargs)
        return _LockedCursor(cursor, self._lock)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


class LocalStateStore:
    def __init__(self, db_path: Path, artifacts_dir: Path) -> None:
        self.db_path = db_path
        self.artifacts_dir = artifacts_dir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._conn = _LockedConnection(sqlite3.connect(self.db_path, check_same_thread=False))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                session_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                objective TEXT NOT NULL,
                profile TEXT NOT NULL,
                cwd TEXT NOT NULL,
                status TEXT NOT NULL,
                phase TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS traces (
                trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                artifact_path TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT NOT NULL,
                profile TEXT NOT NULL,
                cwd TEXT NOT NULL,
                status TEXT NOT NULL,
                last_run_id TEXT
            );

            CREATE TABLE IF NOT EXISTS session_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                run_id TEXT,
                metadata_json TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS session_events (
                session_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                run_id TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS memory_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                session_id TEXT,
                subagent_id TEXT,
                timestamp TEXT NOT NULL,
                namespace TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                block_count INTEGER NOT NULL,
                artifact_path TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS provider_calls (
                provider_call_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                session_id TEXT,
                subagent_id TEXT,
                timestamp TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                endpoint_style TEXT NOT NULL,
                status TEXT NOT NULL,
                request_artifact_path TEXT NOT NULL,
                response_artifact_path TEXT,
                summary TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS tool_calls (
                tool_call_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                session_id TEXT,
                subagent_id TEXT,
                timestamp TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                call_id TEXT,
                ok INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                artifact_path TEXT,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS disclosures (
                disclosure_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                session_id TEXT,
                subagent_id TEXT,
                timestamp TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                require_approval INTEGER NOT NULL,
                artifact_path TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS subagent_runs (
                subagent_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                session_id TEXT,
                agent_name TEXT NOT NULL,
                namespace TEXT NOT NULL,
                subgoal TEXT,
                status TEXT NOT NULL,
                merged_summary TEXT NOT NULL DEFAULT '',
                artifact_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS subagent_results (
                subagent_result_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subagent_run_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                success INTEGER NOT NULL,
                summary TEXT NOT NULL,
                structured_output_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                artifact_path TEXT,
                FOREIGN KEY(subagent_run_id) REFERENCES subagent_runs(subagent_run_id)
            );

            CREATE TABLE IF NOT EXISTS subagent_provider_artifacts (
                subagent_provider_artifact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subagent_run_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                provider TEXT NOT NULL,
                definition_json TEXT NOT NULL,
                invocation_json TEXT NOT NULL,
                notes_json TEXT NOT NULL,
                artifact_path TEXT,
                FOREIGN KEY(subagent_run_id) REFERENCES subagent_runs(subagent_run_id)
            );

            CREATE TABLE IF NOT EXISTS mcp_sessions (
                mcp_session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_name TEXT NOT NULL,
                transport TEXT NOT NULL,
                config_signature TEXT NOT NULL,
                protocol_version TEXT NOT NULL,
                session_identifier TEXT,
                status TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(server_name, config_signature)
            );

            CREATE TABLE IF NOT EXISTS mcp_messages (
                mcp_message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mcp_session_id INTEGER NOT NULL,
                run_id TEXT,
                session_id TEXT,
                created_at TEXT NOT NULL,
                direction TEXT NOT NULL,
                message_type TEXT NOT NULL,
                method TEXT,
                request_id TEXT,
                payload_json TEXT NOT NULL,
                artifact_path TEXT,
                FOREIGN KEY(mcp_session_id) REFERENCES mcp_sessions(mcp_session_id)
            );

            CREATE TABLE IF NOT EXISTS mcp_stream_events (
                mcp_stream_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mcp_session_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                event_name TEXT NOT NULL,
                event_id TEXT,
                payload_json TEXT NOT NULL,
                artifact_path TEXT,
                FOREIGN KEY(mcp_session_id) REFERENCES mcp_sessions(mcp_session_id)
            );

            CREATE TABLE IF NOT EXISTS mcp_capabilities (
                mcp_capability_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mcp_session_id INTEGER NOT NULL,
                direction TEXT NOT NULL,
                capabilities_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(mcp_session_id) REFERENCES mcp_sessions(mcp_session_id)
            );

            CREATE TABLE IF NOT EXISTS mcp_auth_tokens (
                mcp_auth_token_id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_name TEXT NOT NULL,
                token_kind TEXT NOT NULL,
                token_ref TEXT NOT NULL,
                expires_at TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(server_name, token_kind, token_ref)
            );
            """
        )
        self._ensure_column("runs", "session_id", "TEXT")
        self._ensure_column("memory_snapshots", "session_id", "TEXT")
        self._ensure_column("memory_snapshots", "subagent_id", "TEXT")
        self._ensure_column("provider_calls", "session_id", "TEXT")
        self._ensure_column("provider_calls", "subagent_id", "TEXT")
        self._ensure_column("tool_calls", "session_id", "TEXT")
        self._ensure_column("tool_calls", "subagent_id", "TEXT")
        self._ensure_column("disclosures", "session_id", "TEXT")
        self._ensure_column("disclosures", "subagent_id", "TEXT")
        self._conn.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        existing = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column in existing:
            return
        self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_run(self, *, objective: str, profile: str, cwd: Path, session_id: str | None = None) -> RunSummary:
        now = utc_now()
        run_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO runs(run_id, session_id, created_at, updated_at, objective, profile, cwd, status, phase, summary, error)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, '', NULL)
            """,
            (run_id, session_id, now.isoformat(), now.isoformat(), objective, profile, str(cwd), RunStatus.CREATED.value, "intake"),
        )
        self._conn.commit()
        return RunSummary(
            run_id=run_id,
            created_at=now,
            updated_at=now,
            objective=objective,
            profile=profile,
            cwd=cwd,
            status=RunStatus.CREATED,
            phase="intake",
        )

    def update_run(
        self,
        run_id: str,
        *,
        status: RunStatus | None = None,
        phase: str | None = None,
        summary: str | None = None,
        error: str | None = None,
    ) -> RunSummary:
        current = self.get_run(run_id)
        updated_at = utc_now()
        new_status = status or current.status
        new_phase = phase or current.phase
        new_summary = summary if summary is not None else current.summary
        new_error = error if error is not None else current.error
        self._conn.execute(
            """
            UPDATE runs
            SET updated_at = ?, status = ?, phase = ?, summary = ?, error = ?
            WHERE run_id = ?
            """,
            (
                updated_at.isoformat(),
                new_status.value,
                new_phase,
                new_summary,
                new_error,
                run_id,
            ),
        )
        self._conn.commit()
        return self.get_run(run_id)

    def save_artifact(self, run_id: str, label: str, payload: Any, suffix: str = "json") -> Path:
        safe_label = label.replace("/", "_").replace(" ", "_")
        run_dir = self.artifacts_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{safe_label}.{suffix}"
        sanitized = _sanitize(payload)
        if suffix == "json":
            text = json.dumps(sanitized, ensure_ascii=False, indent=2, default=str)
        else:
            text = str(sanitized)
        path.write_text(text + ("" if text.endswith("\n") else "\n"), encoding="utf-8")
        return path

    def append_trace(
        self,
        run_id: str,
        *,
        kind: TraceKind,
        message: str,
        payload: dict[str, Any] | None = None,
        artifact_path: Path | None = None,
    ) -> TraceRecord:
        timestamp = utc_now()
        payload = _sanitize(payload or {})
        cursor = self._conn.execute(
            """
            INSERT INTO traces(run_id, timestamp, kind, message, payload_json, artifact_path)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                timestamp.isoformat(),
                kind.value,
                message,
                json.dumps(payload, ensure_ascii=False, default=str),
                str(artifact_path) if artifact_path else None,
            ),
        )
        self._conn.commit()
        self.update_run(run_id, phase=self._phase_for_kind(kind))
        return TraceRecord(
            trace_id=int(cursor.lastrowid),
            run_id=run_id,
            timestamp=timestamp,
            kind=kind,
            message=message,
            payload=payload,
            artifact_path=str(artifact_path) if artifact_path else None,
        )

    def append_memory_snapshot(
        self,
        run_id: str,
        *,
        session_id: str | None = None,
        subagent_id: str | None = None,
        namespace: str,
        event_count: int,
        block_count: int,
        artifact_path: Path,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO memory_snapshots(run_id, session_id, subagent_id, timestamp, namespace, event_count, block_count, artifact_path)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                session_id,
                subagent_id,
                utc_now().isoformat(),
                namespace,
                event_count,
                block_count,
                str(artifact_path),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def append_provider_call(
        self,
        run_id: str,
        *,
        session_id: str | None = None,
        subagent_id: str | None = None,
        provider: str,
        model: str,
        endpoint_style: str,
        status: str,
        request_artifact_path: Path,
        response_artifact_path: Path | None = None,
        summary: str = "",
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO provider_calls(run_id, session_id, subagent_id, timestamp, provider, model, endpoint_style, status, request_artifact_path, response_artifact_path, summary)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                session_id,
                subagent_id,
                utc_now().isoformat(),
                provider,
                model,
                endpoint_style,
                status,
                str(request_artifact_path),
                str(response_artifact_path) if response_artifact_path else None,
                summary,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def append_tool_call(
        self,
        run_id: str,
        *,
        session_id: str | None = None,
        subagent_id: str | None = None,
        tool_name: str,
        call_id: str | None,
        ok: bool,
        payload: dict[str, Any],
        result: dict[str, Any],
        artifact_path: Path | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO tool_calls(run_id, session_id, subagent_id, timestamp, tool_name, call_id, ok, payload_json, result_json, artifact_path)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                session_id,
                subagent_id,
                utc_now().isoformat(),
                tool_name,
                call_id,
                1 if ok else 0,
                json.dumps(_sanitize(payload), ensure_ascii=False, default=str),
                json.dumps(_sanitize(result), ensure_ascii=False, default=str),
                str(artifact_path) if artifact_path else None,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def append_disclosure(
        self,
        run_id: str,
        *,
        session_id: str | None = None,
        subagent_id: str | None = None,
        title: str,
        summary: str,
        require_approval: bool,
        artifact_path: Path,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO disclosures(run_id, session_id, subagent_id, timestamp, title, summary, require_approval, artifact_path)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                session_id,
                subagent_id,
                utc_now().isoformat(),
                title,
                summary,
                1 if require_approval else 0,
                str(artifact_path),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def create_subagent_run(
        self,
        *,
        run_id: str,
        agent_name: str,
        namespace: str,
        session_id: str | None = None,
        subgoal: str | None = None,
        status: str = "started",
        artifact_path: Path | None = None,
    ) -> int:
        now = utc_now().isoformat()
        cursor = self._conn.execute(
            """
            INSERT INTO subagent_runs(run_id, session_id, agent_name, namespace, subgoal, status, merged_summary, artifact_path, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, '', ?, ?, ?)
            """,
            (
                run_id,
                session_id,
                agent_name,
                namespace,
                subgoal,
                status,
                str(artifact_path) if artifact_path else None,
                now,
                now,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def update_subagent_run(
        self,
        subagent_run_id: int,
        *,
        status: str | None = None,
        merged_summary: str | None = None,
        artifact_path: Path | None = None,
    ) -> None:
        current = self._conn.execute(
            """
            SELECT status, merged_summary, artifact_path
            FROM subagent_runs
            WHERE subagent_run_id = ?
            """,
            (subagent_run_id,),
        ).fetchone()
        if current is None:
            raise KeyError(f"Unknown subagent run id: {subagent_run_id}")
        self._conn.execute(
            """
            UPDATE subagent_runs
            SET status = ?, merged_summary = ?, artifact_path = ?, updated_at = ?
            WHERE subagent_run_id = ?
            """,
            (
                status if status is not None else current["status"],
                merged_summary if merged_summary is not None else current["merged_summary"],
                str(artifact_path) if artifact_path else current["artifact_path"],
                utc_now().isoformat(),
                subagent_run_id,
            ),
        )
        self._conn.commit()

    def append_subagent_result(
        self,
        subagent_run_id: int,
        *,
        agent_name: str,
        success: bool,
        summary: str,
        structured_output: dict[str, Any],
        evidence: list[str],
        artifact_path: Path | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO subagent_results(subagent_run_id, created_at, agent_name, success, summary, structured_output_json, evidence_json, artifact_path)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subagent_run_id,
                utc_now().isoformat(),
                agent_name,
                1 if success else 0,
                summary,
                json.dumps(_sanitize(structured_output), ensure_ascii=False, default=str),
                json.dumps(_sanitize(evidence), ensure_ascii=False, default=str),
                str(artifact_path) if artifact_path else None,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def append_subagent_provider_artifact(
        self,
        subagent_run_id: int,
        *,
        provider: str,
        definition: Any,
        invocation: Any,
        notes: list[str],
        artifact_path: Path | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO subagent_provider_artifacts(subagent_run_id, created_at, provider, definition_json, invocation_json, notes_json, artifact_path)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subagent_run_id,
                utc_now().isoformat(),
                provider,
                json.dumps(_sanitize(definition), ensure_ascii=False, default=str),
                json.dumps(_sanitize(invocation), ensure_ascii=False, default=str),
                json.dumps(_sanitize(notes), ensure_ascii=False, default=str),
                str(artifact_path) if artifact_path else None,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def list_subagent_runs(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT subagent_run_id, run_id, session_id, agent_name, namespace, subgoal, status, merged_summary, artifact_path, created_at, updated_at
            FROM subagent_runs
            WHERE run_id = ?
            ORDER BY subagent_run_id ASC
            """,
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_subagent_provider_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT spa.subagent_provider_artifact_id, spa.subagent_run_id, spa.created_at, spa.provider,
                   spa.definition_json, spa.invocation_json, spa.notes_json, spa.artifact_path
            FROM subagent_provider_artifacts spa
            JOIN subagent_runs sr ON sr.subagent_run_id = spa.subagent_run_id
            WHERE sr.run_id = ?
            ORDER BY spa.subagent_provider_artifact_id ASC
            """,
            (run_id,),
        ).fetchall()
        artifacts: list[dict[str, Any]] = []
        for row in rows:
            artifacts.append(
                {
                    "subagent_provider_artifact_id": row["subagent_provider_artifact_id"],
                    "subagent_run_id": row["subagent_run_id"],
                    "created_at": row["created_at"],
                    "provider": row["provider"],
                    "definition": json.loads(row["definition_json"]),
                    "invocation": json.loads(row["invocation_json"]),
                    "notes": json.loads(row["notes_json"]),
                    "artifact_path": row["artifact_path"],
                }
            )
        return artifacts

    def list_runs(self, limit: int = 20) -> list[RunSummary]:
        rows = self._conn.execute(
            """
            SELECT run_id, created_at, updated_at, objective, profile, cwd, status, phase, summary, error
            FROM runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_run(self, run_id: str) -> RunSummary:
        row = self._conn.execute(
            """
            SELECT run_id, created_at, updated_at, objective, profile, cwd, status, phase, summary, error
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown run id: {run_id}")
        return self._row_to_run(row)

    def list_traces(self, run_id: str) -> list[TraceRecord]:
        rows = self._conn.execute(
            """
            SELECT trace_id, run_id, timestamp, kind, message, payload_json, artifact_path
            FROM traces
            WHERE run_id = ?
            ORDER BY trace_id ASC
            """,
            (run_id,),
        ).fetchall()
        traces: list[TraceRecord] = []
        for row in rows:
            traces.append(
                TraceRecord(
                    trace_id=int(row["trace_id"]),
                    run_id=row["run_id"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    kind=TraceKind(row["kind"]),
                    message=row["message"],
                    payload=json.loads(row["payload_json"]),
                    artifact_path=row["artifact_path"],
                )
            )
        return traces

    def create_session(self, *, title: str, profile: str, cwd: Path, status: str = "active") -> str:
        session_id = uuid.uuid4().hex
        now = utc_now().isoformat()
        self._conn.execute(
            """
            INSERT INTO sessions(session_id, created_at, updated_at, title, profile, cwd, status, last_run_id)
            VALUES(?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (session_id, now, now, title, profile, str(cwd), status),
        )
        self._conn.commit()
        return session_id

    def list_sessions(self, limit: int = 50) -> list[SessionSummary]:
        rows = self._conn.execute(
            """
            SELECT session_id, created_at, updated_at, title, profile, cwd, status, last_run_id
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def get_session(self, session_id: str) -> SessionSummary:
        row = self._conn.execute(
            """
            SELECT session_id, created_at, updated_at, title, profile, cwd, status, last_run_id
            FROM sessions
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown session id: {session_id}")
        return self._row_to_session(row)

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        profile: str | None = None,
        status: str | None = None,
        last_run_id: str | None = None,
    ) -> SessionSummary:
        current = self.get_session(session_id)
        self._conn.execute(
            """
            UPDATE sessions
            SET updated_at = ?, title = ?, profile = ?, status = ?, last_run_id = ?
            WHERE session_id = ?
            """,
            (
                utc_now().isoformat(),
                title if title is not None else current.title,
                profile if profile is not None else current.profile,
                status if status is not None else current.status,
                last_run_id if last_run_id is not None else current.last_run_id,
                session_id,
            ),
        )
        self._conn.commit()
        return self.get_session(session_id)

    def append_session_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO session_messages(session_id, created_at, role, content, run_id, metadata_json)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                utc_now().isoformat(),
                role,
                content,
                run_id,
                json.dumps(_sanitize(metadata or {}), ensure_ascii=False, default=str),
            ),
        )
        self._conn.commit()
        self._conn.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (utc_now().isoformat(), session_id))
        self._conn.commit()
        return int(cursor.lastrowid)

    def list_session_messages(self, session_id: str, limit: int = 200) -> list[SessionMessageRecord]:
        rows = self._conn.execute(
            """
            SELECT message_id, session_id, created_at, role, content, run_id, metadata_json
            FROM session_messages
            WHERE session_id = ?
            ORDER BY message_id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [
            SessionMessageRecord(
                message_id=int(row["message_id"]),
                session_id=row["session_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                role=row["role"],
                content=row["content"],
                run_id=row["run_id"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def append_session_event(
        self,
        session_id: str,
        *,
        name: str,
        payload: dict[str, Any],
        run_id: str | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO session_events(session_id, created_at, name, payload_json, run_id)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                session_id,
                utc_now().isoformat(),
                name,
                json.dumps(_sanitize(payload), ensure_ascii=False, default=str),
                run_id,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def list_session_events(self, session_id: str, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT session_event_id, session_id, created_at, name, payload_json, run_id
            FROM session_events
            WHERE session_id = ?
            ORDER BY session_event_id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [
            {
                "session_event_id": row["session_event_id"],
                "session_id": row["session_id"],
                "created_at": row["created_at"],
                "name": row["name"],
                "payload": json.loads(row["payload_json"]),
                "run_id": row["run_id"],
            }
            for row in rows
        ]

    def upsert_mcp_session(
        self,
        *,
        server_name: str,
        transport: str,
        config_signature: str,
        protocol_version: str,
        session_identifier: str | None,
        status: str,
        capabilities: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = utc_now().isoformat()
        current = self._conn.execute(
            """
            SELECT mcp_session_id
            FROM mcp_sessions
            WHERE server_name = ? AND config_signature = ?
            """,
            (server_name, config_signature),
        ).fetchone()
        payload_capabilities = json.dumps(_sanitize(capabilities or {}), ensure_ascii=False, default=str)
        payload_metadata = json.dumps(_sanitize(metadata or {}), ensure_ascii=False, default=str)
        if current is None:
            cursor = self._conn.execute(
                """
                INSERT INTO mcp_sessions(
                    server_name, transport, config_signature, protocol_version, session_identifier,
                    status, capabilities_json, metadata_json, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    server_name,
                    transport,
                    config_signature,
                    protocol_version,
                    session_identifier,
                    status,
                    payload_capabilities,
                    payload_metadata,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid)
        self._conn.execute(
            """
            UPDATE mcp_sessions
            SET transport = ?, protocol_version = ?, session_identifier = ?, status = ?,
                capabilities_json = ?, metadata_json = ?, updated_at = ?
            WHERE mcp_session_id = ?
            """,
            (
                transport,
                protocol_version,
                session_identifier,
                status,
                payload_capabilities,
                payload_metadata,
                now,
                int(current["mcp_session_id"]),
            ),
        )
        self._conn.commit()
        return int(current["mcp_session_id"])

    def append_mcp_message(
        self,
        mcp_session_id: int,
        *,
        direction: str,
        message_type: str,
        payload: dict[str, Any],
        method: str | None = None,
        request_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        artifact_path: Path | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO mcp_messages(
                mcp_session_id, run_id, session_id, created_at, direction,
                message_type, method, request_id, payload_json, artifact_path
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mcp_session_id,
                run_id,
                session_id,
                utc_now().isoformat(),
                direction,
                message_type,
                method,
                request_id,
                json.dumps(_sanitize(payload), ensure_ascii=False, default=str),
                str(artifact_path) if artifact_path else None,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def append_mcp_stream_event(
        self,
        mcp_session_id: int,
        *,
        event_name: str,
        payload: dict[str, Any],
        event_id: str | None = None,
        artifact_path: Path | None = None,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO mcp_stream_events(mcp_session_id, created_at, event_name, event_id, payload_json, artifact_path)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                mcp_session_id,
                utc_now().isoformat(),
                event_name,
                event_id,
                json.dumps(_sanitize(payload), ensure_ascii=False, default=str),
                str(artifact_path) if artifact_path else None,
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def append_mcp_capabilities(self, mcp_session_id: int, *, direction: str, capabilities: dict[str, Any]) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO mcp_capabilities(mcp_session_id, direction, capabilities_json, created_at)
            VALUES(?, ?, ?, ?)
            """,
            (
                mcp_session_id,
                direction,
                json.dumps(_sanitize(capabilities), ensure_ascii=False, default=str),
                utc_now().isoformat(),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def upsert_mcp_auth_token(
        self,
        *,
        server_name: str,
        token_kind: str,
        token_ref: str,
        expires_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        now = utc_now().isoformat()
        current = self._conn.execute(
            """
            SELECT mcp_auth_token_id
            FROM mcp_auth_tokens
            WHERE server_name = ? AND token_kind = ? AND token_ref = ?
            """,
            (server_name, token_kind, token_ref),
        ).fetchone()
        payload = json.dumps(_sanitize(metadata or {}), ensure_ascii=False, default=str)
        if current is None:
            cursor = self._conn.execute(
                """
                INSERT INTO mcp_auth_tokens(server_name, token_kind, token_ref, expires_at, metadata_json, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (server_name, token_kind, token_ref, expires_at, payload, now, now),
            )
            self._conn.commit()
            return int(cursor.lastrowid)
        self._conn.execute(
            """
            UPDATE mcp_auth_tokens
            SET expires_at = ?, metadata_json = ?, updated_at = ?
            WHERE mcp_auth_token_id = ?
            """,
            (expires_at, payload, now, int(current["mcp_auth_token_id"])),
        )
        self._conn.commit()
        return int(current["mcp_auth_token_id"])

    def list_mcp_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT mcp_session_id, server_name, transport, config_signature, protocol_version,
                   session_identifier, status, capabilities_json, metadata_json, created_at, updated_at
            FROM mcp_sessions
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "mcp_session_id": row["mcp_session_id"],
                "server_name": row["server_name"],
                "transport": row["transport"],
                "config_signature": row["config_signature"],
                "protocol_version": row["protocol_version"],
                "session_identifier": row["session_identifier"],
                "status": row["status"],
                "capabilities": json.loads(row["capabilities_json"]),
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def list_mcp_messages(self, mcp_session_id: int, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT mcp_message_id, mcp_session_id, run_id, session_id, created_at, direction,
                   message_type, method, request_id, payload_json, artifact_path
            FROM mcp_messages
            WHERE mcp_session_id = ?
            ORDER BY mcp_message_id ASC
            LIMIT ?
            """,
            (mcp_session_id, limit),
        ).fetchall()
        return [
            {
                "mcp_message_id": row["mcp_message_id"],
                "mcp_session_id": row["mcp_session_id"],
                "run_id": row["run_id"],
                "session_id": row["session_id"],
                "created_at": row["created_at"],
                "direction": row["direction"],
                "message_type": row["message_type"],
                "method": row["method"],
                "request_id": row["request_id"],
                "payload": json.loads(row["payload_json"]),
                "artifact_path": row["artifact_path"],
            }
            for row in rows
        ]

    def list_mcp_stream_events(self, mcp_session_id: int, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT mcp_stream_event_id, mcp_session_id, created_at, event_name, event_id, payload_json, artifact_path
            FROM mcp_stream_events
            WHERE mcp_session_id = ?
            ORDER BY mcp_stream_event_id ASC
            LIMIT ?
            """,
            (mcp_session_id, limit),
        ).fetchall()
        return [
            {
                "mcp_stream_event_id": row["mcp_stream_event_id"],
                "mcp_session_id": row["mcp_session_id"],
                "created_at": row["created_at"],
                "event_name": row["event_name"],
                "event_id": row["event_id"],
                "payload": json.loads(row["payload_json"]),
                "artifact_path": row["artifact_path"],
            }
            for row in rows
        ]

    def load_artifact(self, artifact_path: str | Path) -> str:
        return Path(artifact_path).read_text(encoding="utf-8")

    def close(self) -> None:
        self._conn.close()

    def _row_to_run(self, row: sqlite3.Row) -> RunSummary:
        return RunSummary(
            run_id=row["run_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            objective=row["objective"],
            profile=row["profile"],
            cwd=Path(row["cwd"]),
            status=RunStatus(row["status"]),
            phase=row["phase"],
            summary=row["summary"],
            error=row["error"],
        )

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> SessionSummary:
        return SessionSummary(
            session_id=row["session_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            title=row["title"],
            profile=row["profile"],
            cwd=Path(row["cwd"]),
            status=row["status"],
            last_run_id=row["last_run_id"],
        )

    @staticmethod
    def _phase_for_kind(kind: TraceKind) -> str:
        if kind == TraceKind.PLAN:
            return "planning"
        if kind in {TraceKind.MEMORY, TraceKind.PROVIDER_REQUEST, TraceKind.PROVIDER_RESPONSE, TraceKind.TOOL}:
            return "execution"
        if kind == TraceKind.DISCLOSURE:
            return "reporting"
        return "intake"
