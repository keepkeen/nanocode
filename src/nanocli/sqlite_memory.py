from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import json
import sqlite3

from agent_memory_os.base import BaseEventStore
from agent_memory_os.models import BlockKind, BlockPlane, EventRecord, MemoryBlock, MessageRole, RetrievalHit
from agent_memory_os.utils import cosine_sparse, lexical_overlap, normalize_terms, rrf_score, sparse_embed


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _candidate_evidence_key(evidence: Dict[str, object]) -> str:
    event_id = evidence.get("event_id")
    if event_id:
        return f"event:{event_id}"
    source = str(evidence.get("source", "unknown"))
    source_ref = (
        evidence.get("source_ref")
        or evidence.get("source_key")
        or evidence.get("resource_name")
        or evidence.get("source_path")
        or evidence.get("content_hash")
        or evidence.get("session_namespace")
        or "unknown"
    )
    return f"{source}:{source_ref}"


class SQLiteEventStore(BaseEventStore):
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                namespace TEXT NOT NULL,
                event_id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS blocks (
                namespace TEXT NOT NULL,
                block_id TEXT PRIMARY KEY,
                plane TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                salience REAL NOT NULL,
                stability REAL NOT NULL,
                confidence REAL NOT NULL,
                source_event_ids_json TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                references_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                supersedes TEXT,
                active INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS block_refs (
                namespace TEXT NOT NULL,
                block_id TEXT NOT NULL,
                ref_value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS execution_state (
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY(namespace, key)
            );

            CREATE TABLE IF NOT EXISTS memory_sources (
                source_id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                source_key TEXT NOT NULL,
                source_path TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(namespace, source_key)
            );

            CREATE TABLE IF NOT EXISTS derived_project_resources (
                resource_id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                resource_name TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(namespace, resource_name)
            );

            CREATE TABLE IF NOT EXISTS memory_candidates (
                candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                normalized_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                source_types_json TEXT NOT NULL,
                salience REAL NOT NULL,
                stability REAL NOT NULL,
                confidence REAL NOT NULL,
                promoted_block_id TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                UNIQUE(namespace, normalized_key)
            );
            """
        )
        self._conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_blocks
            USING fts5(block_id UNINDEXED, namespace UNINDEXED, text, tags, refs)
            """
        )
        self._conn.commit()

    def append_event(self, event: EventRecord) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO events(namespace, event_id, role, content, source, metadata_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.namespace,
                event.event_id,
                event.role.value,
                event.content,
                event.source,
                _json_dump(event.metadata),
                event.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def upsert_block(self, block: MemoryBlock) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO blocks(
                namespace, block_id, plane, kind, text, salience, stability, confidence,
                source_event_ids_json, tags_json, references_json, metadata_json, created_at,
                supersedes, active
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                block.namespace,
                block.block_id,
                block.plane.value,
                block.kind.value,
                block.text,
                block.salience,
                block.stability,
                block.confidence,
                _json_dump(block.source_event_ids),
                _json_dump(block.tags),
                _json_dump(block.references),
                _json_dump(block.metadata),
                block.created_at.isoformat(),
                block.supersedes,
                1 if block.active else 0,
            ),
        )
        self._replace_refs(block)
        self._replace_fts(block)
        self._conn.commit()

    def supersede_block(self, old_block_id: str, new_block: MemoryBlock) -> None:
        self._conn.execute("UPDATE blocks SET active = 0 WHERE block_id = ?", (old_block_id,))
        new_block.supersedes = old_block_id
        self.upsert_block(new_block)

    def deactivate_block(self, block_id: str) -> None:
        self._conn.execute("UPDATE blocks SET active = 0 WHERE block_id = ?", (block_id,))
        self._conn.commit()

    def list_events(self, namespace: str) -> List[EventRecord]:
        rows = self._conn.execute(
            """
            SELECT namespace, event_id, role, content, source, metadata_json, created_at
            FROM events
            WHERE namespace = ?
            ORDER BY created_at ASC
            """,
            (namespace,),
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def list_blocks(self, namespace: str, active_only: bool = True) -> List[MemoryBlock]:
        sql = """
            SELECT namespace, block_id, plane, kind, text, salience, stability, confidence,
                   source_event_ids_json, tags_json, references_json, metadata_json, created_at,
                   supersedes, active
            FROM blocks
            WHERE namespace = ?
        """
        params: list[object] = [namespace]
        if active_only:
            sql += " AND active = 1"
        sql += " ORDER BY created_at ASC"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_block(row) for row in rows]

    def list_control_blocks(self, namespace: str) -> List[MemoryBlock]:
        return [block for block in self.list_blocks(namespace) if block.plane == BlockPlane.CONTROL]

    def list_execution_blocks(self, namespace: str) -> List[MemoryBlock]:
        return [block for block in self.list_blocks(namespace) if block.plane == BlockPlane.EXECUTION]

    def set_execution_value(self, namespace: str, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO execution_state(namespace, key, value)
            VALUES(?, ?, ?)
            """,
            (namespace, key, value),
        )
        self._conn.commit()

    def get_execution_state(self, namespace: str) -> Dict[str, str]:
        rows = self._conn.execute(
            "SELECT key, value FROM execution_state WHERE namespace = ?",
            (namespace,),
        ).fetchall()
        return {row["key"]: row["value"] for row in rows}

    def delete_execution_value(self, namespace: str, key: str) -> None:
        self._conn.execute(
            "DELETE FROM execution_state WHERE namespace = ? AND key = ?",
            (namespace, key),
        )
        self._conn.commit()

    def replace_execution_state(self, namespace: str, values: Dict[str, str]) -> None:
        self._conn.execute("DELETE FROM execution_state WHERE namespace = ?", (namespace,))
        for key, value in values.items():
            self._conn.execute(
                """
                INSERT INTO execution_state(namespace, key, value)
                VALUES(?, ?, ?)
                """,
                (namespace, key, value),
            )
        self._conn.commit()

    def candidate_blocks(self, namespace: str, query: str, limit: int = 64) -> List[MemoryBlock]:
        terms = [term.replace('"', " ") for term in normalize_terms(query)]
        if not terms:
            return self.list_blocks(namespace)[:limit]
        expression = " OR ".join(f'"{term}"' for term in terms[:8])
        try:
            rows = self._conn.execute(
                """
                SELECT b.namespace, b.block_id, b.plane, b.kind, b.text, b.salience, b.stability, b.confidence,
                       b.source_event_ids_json, b.tags_json, b.references_json, b.metadata_json, b.created_at,
                       b.supersedes, b.active
                FROM fts_blocks f
                JOIN blocks b ON b.block_id = f.block_id
                WHERE f.namespace = ? AND fts_blocks MATCH ? AND b.active = 1
                LIMIT ?
                """,
                (namespace, expression, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return self.list_blocks(namespace)[:limit]
        if not rows:
            return self.list_blocks(namespace)[:limit]
        return [self._row_to_block(row) for row in rows]

    def namespaces(self) -> List[str]:
        rows = self._conn.execute("SELECT DISTINCT namespace FROM events UNION SELECT DISTINCT namespace FROM blocks").fetchall()
        return [row[0] for row in rows]

    def replace_memory_sources(self, namespace: str, sources: List[Dict[str, object]]) -> None:
        active_keys = {str(source["source_key"]) for source in sources}
        rows = self._conn.execute(
            "SELECT source_key FROM memory_sources WHERE namespace = ?",
            (namespace,),
        ).fetchall()
        for row in rows:
            source_key = str(row["source_key"])
            if source_key not in active_keys:
                self._conn.execute(
                    "DELETE FROM memory_sources WHERE namespace = ? AND source_key = ?",
                    (namespace, source_key),
                )
        for source in sources:
            self._conn.execute(
                """
                INSERT INTO memory_sources(namespace, source_key, source_path, source_kind, content, content_hash, metadata_json, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, source_key) DO UPDATE SET
                    source_path = excluded.source_path,
                    source_kind = excluded.source_kind,
                    content = excluded.content,
                    content_hash = excluded.content_hash,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    namespace,
                    str(source["source_key"]),
                    str(source["source_path"]),
                    str(source["source_kind"]),
                    str(source["content"]),
                    str(source["content_hash"]),
                    _json_dump(source.get("metadata", {})),
                    _utcnow().isoformat(),
                ),
            )
        self._conn.commit()

    def list_memory_sources(self, namespace: str) -> List[Dict[str, object]]:
        rows = self._conn.execute(
            """
            SELECT source_id, namespace, source_key, source_path, source_kind, content, content_hash, metadata_json, updated_at
            FROM memory_sources
            WHERE namespace = ?
            ORDER BY source_path ASC
            """,
            (namespace,),
        ).fetchall()
        return [
            {
                "source_id": row["source_id"],
                "namespace": row["namespace"],
                "source_key": row["source_key"],
                "source_path": row["source_path"],
                "source_kind": row["source_kind"],
                "content": row["content"],
                "content_hash": row["content_hash"],
                "metadata": json.loads(row["metadata_json"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def replace_derived_project_resources(self, namespace: str, resources: List[Dict[str, object]]) -> None:
        active_names = {str(resource["resource_name"]) for resource in resources}
        rows = self._conn.execute(
            "SELECT resource_name FROM derived_project_resources WHERE namespace = ?",
            (namespace,),
        ).fetchall()
        for row in rows:
            resource_name = str(row["resource_name"])
            if resource_name not in active_names:
                self._conn.execute(
                    "DELETE FROM derived_project_resources WHERE namespace = ? AND resource_name = ?",
                    (namespace, resource_name),
                )
        for resource in resources:
            self._conn.execute(
                """
                INSERT INTO derived_project_resources(namespace, resource_name, content, content_hash, metadata_json, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, resource_name) DO UPDATE SET
                    content = excluded.content,
                    content_hash = excluded.content_hash,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    namespace,
                    str(resource["resource_name"]),
                    str(resource["content"]),
                    str(resource["content_hash"]),
                    _json_dump(resource.get("metadata", {})),
                    _utcnow().isoformat(),
                ),
            )
        self._conn.commit()

    def list_derived_project_resources(self, namespace: str) -> List[Dict[str, object]]:
        rows = self._conn.execute(
            """
            SELECT resource_id, namespace, resource_name, content, content_hash, metadata_json, updated_at
            FROM derived_project_resources
            WHERE namespace = ?
            ORDER BY resource_name ASC
            """,
            (namespace,),
        ).fetchall()
        return [
            {
                "resource_id": row["resource_id"],
                "namespace": row["namespace"],
                "resource_name": row["resource_name"],
                "content": row["content"],
                "content_hash": row["content_hash"],
                "metadata": json.loads(row["metadata_json"]),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def record_memory_candidate(
        self,
        *,
        namespace: str,
        normalized_key: str,
        kind: str,
        text: str,
        evidence: Dict[str, object],
        salience: float,
        stability: float,
        confidence: float,
    ) -> Dict[str, object]:
        now = _utcnow().isoformat()
        row = self._conn.execute(
            """
            SELECT candidate_id, namespace, normalized_key, kind, text, status, evidence_json, source_types_json,
                   salience, stability, confidence, promoted_block_id, first_seen_at, last_seen_at
            FROM memory_candidates
            WHERE namespace = ? AND normalized_key = ?
            """,
            (namespace, normalized_key),
        ).fetchone()
        if row is None:
            evidence_items = [evidence]
            source_types = sorted({str(evidence.get("source", "conversation"))})
            cursor = self._conn.execute(
                """
                INSERT INTO memory_candidates(
                    namespace, normalized_key, kind, text, status, evidence_json, source_types_json,
                    salience, stability, confidence, promoted_block_id, first_seen_at, last_seen_at
                )
                VALUES(?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    namespace,
                    normalized_key,
                    kind,
                    text,
                    _json_dump(evidence_items),
                    _json_dump(source_types),
                    salience,
                    stability,
                    confidence,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return self.get_memory_candidate(int(cursor.lastrowid))
        evidence_items = json.loads(row["evidence_json"])
        if all(_candidate_evidence_key(existing) != _candidate_evidence_key(evidence) for existing in evidence_items):
            evidence_items.append(evidence)
        source_types = sorted({*json.loads(row["source_types_json"]), str(evidence.get("source", "conversation"))})
        self._conn.execute(
            """
            UPDATE memory_candidates
            SET text = ?, evidence_json = ?, source_types_json = ?, salience = ?, stability = ?,
                confidence = ?, last_seen_at = ?
            WHERE candidate_id = ?
            """,
            (
                text,
                _json_dump(evidence_items),
                _json_dump(source_types),
                max(float(row["salience"]), salience),
                max(float(row["stability"]), stability),
                max(float(row["confidence"]), confidence),
                now,
                int(row["candidate_id"]),
            ),
        )
        self._conn.commit()
        return self.get_memory_candidate(int(row["candidate_id"]))

    def get_memory_candidate(self, candidate_id: int) -> Dict[str, object]:
        row = self._conn.execute(
            """
            SELECT candidate_id, namespace, normalized_key, kind, text, status, evidence_json, source_types_json,
                   salience, stability, confidence, promoted_block_id, first_seen_at, last_seen_at
            FROM memory_candidates
            WHERE candidate_id = ?
            """,
            (candidate_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown memory candidate id: {candidate_id}")
        return {
            "candidate_id": row["candidate_id"],
            "namespace": row["namespace"],
            "normalized_key": row["normalized_key"],
            "kind": row["kind"],
            "text": row["text"],
            "status": row["status"],
            "evidence": json.loads(row["evidence_json"]),
            "source_types": json.loads(row["source_types_json"]),
            "salience": float(row["salience"]),
            "stability": float(row["stability"]),
            "confidence": float(row["confidence"]),
            "promoted_block_id": row["promoted_block_id"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
        }

    def list_memory_candidates(self, namespace: str, *, status: str | None = None) -> List[Dict[str, object]]:
        sql = """
            SELECT candidate_id, namespace, normalized_key, kind, text, status, evidence_json, source_types_json,
                   salience, stability, confidence, promoted_block_id, first_seen_at, last_seen_at
            FROM memory_candidates
            WHERE namespace = ?
        """
        params: List[object] = [namespace]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY last_seen_at DESC, candidate_id DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            {
                "candidate_id": row["candidate_id"],
                "namespace": row["namespace"],
                "normalized_key": row["normalized_key"],
                "kind": row["kind"],
                "text": row["text"],
                "status": row["status"],
                "evidence": json.loads(row["evidence_json"]),
                "source_types": json.loads(row["source_types_json"]),
                "salience": float(row["salience"]),
                "stability": float(row["stability"]),
                "confidence": float(row["confidence"]),
                "promoted_block_id": row["promoted_block_id"],
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
            }
            for row in rows
        ]

    def update_memory_candidate_status(self, candidate_id: int, *, status: str, promoted_block_id: str | None = None) -> None:
        self._conn.execute(
            """
            UPDATE memory_candidates
            SET status = ?, promoted_block_id = ?
            WHERE candidate_id = ?
            """,
            (status, promoted_block_id, candidate_id),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _replace_refs(self, block: MemoryBlock) -> None:
        self._conn.execute("DELETE FROM block_refs WHERE block_id = ?", (block.block_id,))
        for ref_value in block.references:
            self._conn.execute(
                "INSERT INTO block_refs(namespace, block_id, ref_value) VALUES(?, ?, ?)",
                (block.namespace, block.block_id, ref_value),
            )

    def _replace_fts(self, block: MemoryBlock) -> None:
        self._conn.execute("DELETE FROM fts_blocks WHERE block_id = ?", (block.block_id,))
        self._conn.execute(
            """
            INSERT INTO fts_blocks(block_id, namespace, text, tags, refs)
            VALUES(?, ?, ?, ?, ?)
            """,
            (
                block.block_id,
                block.namespace,
                block.text,
                " ".join(block.tags),
                " ".join(block.references),
            ),
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> EventRecord:
        return EventRecord(
            namespace=row["namespace"],
            role=MessageRole(row["role"]),
            content=row["content"],
            source=row["source"],
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            event_id=row["event_id"],
        )

    @staticmethod
    def _row_to_block(row: sqlite3.Row) -> MemoryBlock:
        return MemoryBlock(
            namespace=row["namespace"],
            plane=BlockPlane(row["plane"]),
            kind=BlockKind(row["kind"]),
            text=row["text"],
            salience=float(row["salience"]),
            stability=float(row["stability"]),
            confidence=float(row["confidence"]),
            source_event_ids=json.loads(row["source_event_ids_json"]),
            tags=json.loads(row["tags_json"]),
            references=json.loads(row["references_json"]),
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            supersedes=row["supersedes"],
            active=bool(row["active"]),
            block_id=row["block_id"],
        )


class SQLiteHybridRetriever:
    def __init__(self, store: SQLiteEventStore) -> None:
        self.store = store

    def retrieve(self, *, namespace: str, query: str, top_k: int) -> List[RetrievalHit]:
        blocks = self.store.candidate_blocks(namespace, query, limit=max(32, top_k * 8))
        if not blocks:
            return []
        query_emb = sparse_embed(query)
        query_terms = set(normalize_terms(query))
        now = _utcnow()

        rows: List[Tuple[MemoryBlock, Dict[str, float]]] = []
        for block in blocks:
            channels: Dict[str, float] = {}
            channels["lexical"] = lexical_overlap(query, block.text + " " + " ".join(block.tags))
            channels["vector"] = cosine_sparse(query_emb, block.embedding())
            channels["graph"] = self._graph_score(block, query_terms)
            channels["salience"] = block.salience
            channels["stability"] = block.stability
            age_hours = max(0.0, (now - block.created_at).total_seconds() / 3600.0)
            channels["recency"] = 1.0 / (1.0 + age_hours / 96.0)
            if block.plane == BlockPlane.CONTROL:
                channels["plane_bonus"] = 0.35
            elif block.kind in {BlockKind.PREFERENCE, BlockKind.DECISION, BlockKind.FACT}:
                channels["plane_bonus"] = 0.18
            else:
                channels["plane_bonus"] = 0.0
            rows.append((block, channels))

        channel_rankings: Dict[str, Dict[str, int]] = defaultdict(dict)
        for channel in ["lexical", "vector", "graph", "salience", "stability", "recency"]:
            ranked = sorted(rows, key=lambda item: item[1][channel], reverse=True)
            for rank, (block, _) in enumerate(ranked, start=1):
                channel_rankings[channel][block.block_id] = rank

        hits: List[RetrievalHit] = []
        for block, channels in rows:
            ranks = [channel_rankings[ch][block.block_id] for ch in channel_rankings]
            fusion = rrf_score(ranks)
            weighted = (
                0.22 * channels["lexical"]
                + 0.18 * channels["vector"]
                + 0.12 * channels["graph"]
                + 0.18 * channels["salience"]
                + 0.14 * channels["stability"]
                + 0.08 * channels["recency"]
                + channels["plane_bonus"]
                + 0.08 * fusion
            )
            hits.append(
                RetrievalHit(
                    block=block,
                    score=weighted,
                    channel_scores=channels,
                    evidence={"rrf": fusion},
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:top_k]

    @staticmethod
    def _graph_score(block: MemoryBlock, query_terms: set[str]) -> float:
        if not query_terms:
            return 0.0
        block_terms = set(normalize_terms(block.text + " " + " ".join(block.tags + block.references)))
        if not block_terms:
            return 0.0
        direct = len(query_terms & block_terms) / max(1, len(query_terms))
        ref_bonus = min(0.3, 0.05 * len(block.references))
        return min(1.0, direct + ref_bonus)
