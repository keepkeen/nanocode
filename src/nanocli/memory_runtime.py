from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
from typing import Iterable
import json
import re

from agent_memory_os import AgentMemoryOS, BlockKind, ContextAssembly, ContextZone, EventRecord, MemoryBlock, Message, MessageRole, ProviderRequest, ToolSchema
from agent_memory_os.compaction import ReversibleDeltaCompactor
from agent_memory_os.models import BlockPlane, RetrievalHit
from agent_memory_os.providers import build_default_adapters
from agent_memory_os.utils import content_address, normalize_terms

from .models import MemoryOptions
from .sqlite_memory import SQLiteEventStore, SQLiteHybridRetriever


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    "artifacts",
    ".egg-info",
    "site-packages",
}
IGNORED_PATH_MARKERS = {
    ".nanocli/generated",
    ".nanocli/artifacts",
    ".nanocli/project_memory.json",
    ".nanocli/state.db",
}


@dataclass(slots=True)
class CompositeMemorySnapshot:
    project_namespace: str
    session_namespace: str | None
    durable_hits: list[RetrievalHit]
    session_hits: list[RetrievalHit]
    assembly: ContextAssembly
    sources: list[dict[str, object]]
    resources: list[dict[str, object]]
    candidates: list[dict[str, object]]


class CompositeMemoryRuntime:
    def __init__(
        self,
        *,
        store: SQLiteEventStore,
        project_namespace: str,
        options: MemoryOptions,
        workspace_root: Path,
    ) -> None:
        self.store = store
        self.project_namespace = project_namespace
        self.options = options
        self.workspace_root = workspace_root.resolve()
        self.retriever = SQLiteHybridRetriever(store)
        self.compactor = ReversibleDeltaCompactor(store)
        self.adapters = build_default_adapters()
        self._last_source_control_keys: list[str] = []
        self._last_stale_source_blocks_removed = 0

    def ensure_project_control(self, *, system_policies: Iterable[str], user_instructions: Iterable[str]) -> None:
        existing = self.store.list_events(self.project_namespace)
        if not any(event.role in {MessageRole.SYSTEM, MessageRole.DEVELOPER} for event in existing):
            for policy in system_policies:
                self.observe(self.project_namespace, Message(role=MessageRole.SYSTEM, content=policy), source="policy")
            for instruction in user_instructions:
                self.observe(self.project_namespace, Message(role=MessageRole.DEVELOPER, content=instruction), source="instruction")
        self.refresh_project_context()

    def refresh_project_context(self) -> None:
        sources = self._scan_project_sources()
        resources = self._derive_project_resources()
        self.store.replace_memory_sources(self.project_namespace, sources)
        self.store.replace_derived_project_resources(self.project_namespace, resources)
        self._sync_project_source_blocks(sources)
        self._corroborate_pending_candidates(sources=sources, resources=resources)

    def observe(self, namespace: str, message: Message, *, source: str = "conversation") -> tuple[EventRecord, list[MemoryBlock]]:
        memory = AgentMemoryOS(
            namespace=namespace,
            store=self.store,
            recent_turns=self.options.recent_turns,
            compaction_event_threshold=self.options.compaction_event_threshold,
        )
        event = EventRecord(
            namespace=namespace,
            role=message.role,
            content=message.content,
            source=source,
            metadata=message.metadata,
        )
        self.store.append_event(event)
        blocks = memory.writer.derive_blocks(namespace, event)
        for block in blocks:
            self._merge_block(block)
        if len(self.store.list_events(namespace)) >= self.options.compaction_event_threshold:
            self.compactor.compact(namespace=namespace)
        return event, blocks

    def observe_session_message(
        self,
        session_namespace: str,
        message: Message,
        *,
        source: str = "conversation",
    ) -> tuple[EventRecord, list[MemoryBlock]]:
        event, blocks = self.observe(session_namespace, message, source=source)
        for block in blocks:
            self._record_candidate(block, session_namespace=session_namespace, event=event, source=source)
        return event, blocks

    def prepare_request(
        self,
        *,
        provider_name: str,
        model: str,
        user_message: str,
        tools: list[ToolSchema],
        session_namespace: str | None = None,
        extra: dict[str, object] | None = None,
        control_messages: list[Message] | None = None,
        top_k: int = 8,
    ) -> tuple[ProviderRequest, CompositeMemorySnapshot]:
        self.refresh_project_context()
        manifest_tools = list(tools)
        extra = extra or {}
        manifest_tools.extend(self._native_manifest_tools(extra))
        self.sync_tool_manifest(manifest_tools)
        durable_hits = self._project_hits(user_message, top_k=top_k)
        session_hits = self._session_hits(session_namespace, user_message, top_k=max(4, top_k // 2))
        sources = self.store.list_memory_sources(self.project_namespace)
        resources = self.store.list_derived_project_resources(self.project_namespace)
        candidates = self.store.list_memory_candidates(self.project_namespace, status="pending")
        assembly = self._compile_assembly(
            user_message=user_message,
            tools=tools,
            session_namespace=session_namespace,
            durable_hits=durable_hits,
            session_hits=session_hits,
            control_messages=control_messages or [],
            sources=sources,
            resources=resources,
        )
        request = self.adapters[provider_name].build_request(model=model, assembly=assembly, tools=tools, extra=extra)
        request.diagnostics["context"] = assembly.diagnostics
        request.diagnostics["retrieval"] = {
            "project": [self._hit_payload(hit) for hit in durable_hits],
            "session": [self._hit_payload(hit) for hit in session_hits],
        }
        request.diagnostics["project_sources"] = [source["source_path"] for source in sources]
        request.diagnostics["project_resources"] = [resource["resource_name"] for resource in resources]
        request.diagnostics["memory_candidates"] = [
            {"candidate_id": item["candidate_id"], "kind": item["kind"], "evidence_count": len(item["evidence"])}
            for item in candidates
        ]
        return request, CompositeMemorySnapshot(
            project_namespace=self.project_namespace,
            session_namespace=session_namespace,
            durable_hits=durable_hits,
            session_hits=session_hits,
            assembly=assembly,
            sources=sources,
            resources=resources,
            candidates=candidates,
        )

    def export_namespace_state(self, namespace: str) -> dict[str, object]:
        payload = {
            "namespace": namespace,
            "events": [
                {
                    "event_id": event.event_id,
                    "role": event.role.value,
                    "content": event.content,
                    "source": event.source,
                    "metadata": event.metadata,
                }
                for event in self.store.list_events(namespace)
            ],
            "blocks": [
                {
                    "block_id": block.block_id,
                    "plane": block.plane.value,
                    "kind": block.kind.value,
                    "text": block.text,
                    "salience": block.salience,
                    "stability": block.stability,
                    "confidence": block.confidence,
                    "active": block.active,
                    "source_event_ids": list(block.source_event_ids),
                    "tags": list(block.tags),
                    "references": list(block.references),
                    "metadata": dict(block.metadata),
                }
                for block in self.store.list_blocks(namespace, active_only=False)
            ],
            "execution_state": self.store.get_execution_state(namespace),
        }
        if namespace == self.project_namespace:
            payload["sources"] = self.store.list_memory_sources(namespace)
            payload["resources"] = self.store.list_derived_project_resources(namespace)
            payload["candidates"] = self.store.list_memory_candidates(namespace)
            payload["source_control_keys"] = list(self._last_source_control_keys)
            payload["stale_source_blocks_removed"] = self._last_stale_source_blocks_removed
        return payload

    def list_project_sources(self) -> list[dict[str, object]]:
        self.refresh_project_context()
        return self.store.list_memory_sources(self.project_namespace)

    def list_project_resources(self) -> list[dict[str, object]]:
        self.refresh_project_context()
        return self.store.list_derived_project_resources(self.project_namespace)

    def list_memory_candidates(self, *, status: str | None = None) -> list[dict[str, object]]:
        return self.store.list_memory_candidates(self.project_namespace, status=status)

    def reject_candidate(self, candidate_id: int) -> dict[str, object]:
        self.store.update_memory_candidate_status(candidate_id, status="rejected")
        return self.store.get_memory_candidate(candidate_id)

    def promote_candidate(self, candidate_id: int, *, manual: bool = False) -> dict[str, object]:
        candidate = self.store.get_memory_candidate(candidate_id)
        block = MemoryBlock(
            namespace=self.project_namespace,
            plane=BlockPlane.DERIVED,
            kind=BlockKind(candidate["kind"]),
            text=str(candidate["text"]),
            salience=max(float(candidate["salience"]), self.options.promotion_min_salience),
            stability=max(float(candidate["stability"]), self.options.promotion_min_stability),
            confidence=float(candidate["confidence"]),
            source_event_ids=[str(item.get("event_id")) for item in candidate["evidence"] if item.get("event_id")],
            tags=["project_memory", "manual" if manual else "auto"],
            references=[],
            metadata={
                "promotion_mode": "manual" if manual else "auto",
                "promotion_evidence": candidate["evidence"],
                "source_types": candidate["source_types"],
            },
        )
        self._merge_block(block)
        self.store.update_memory_candidate_status(candidate_id, status="promoted", promoted_block_id=block.block_id)
        return self.store.get_memory_candidate(candidate_id)

    def sync_tool_manifest(self, tools: list[ToolSchema]) -> None:
        if not tools:
            return
        manifest_text = self._tool_manifest_text(tools)
        self._sync_named_control_block(
            control_key="tool_manifest:runtime",
            kind=BlockKind.TOOL_MANIFEST,
            text=manifest_text,
            tags=["tool_manifest", "runtime"],
            metadata={"scope": "runtime"},
        )

    def _compile_assembly(
        self,
        *,
        user_message: str,
        tools: list[ToolSchema],
        session_namespace: str | None,
        durable_hits: list[RetrievalHit],
        session_hits: list[RetrievalHit],
        control_messages: list[Message],
        sources: list[dict[str, object]],
        resources: list[dict[str, object]],
    ) -> ContextAssembly:
        control_blocks = self._sorted_control_blocks(self.project_namespace)
        project_control = [
            self._block_to_system_message(block)
            for block in control_blocks
            if block.kind != BlockKind.TOOL_MANIFEST
        ]
        source_messages = [self._project_sources_summary_message(sources)] if sources else []
        tool_messages = [
            self._block_to_system_message(block)
            for block in control_blocks
            if block.kind == BlockKind.TOOL_MANIFEST
        ]
        dynamic_control = control_messages
        derived_context = [self._project_resource_message(resource) for resource in resources]
        durable_context = [self._block_to_context_message(hit.block, heading="PROJECT_MEMORY") for hit in durable_hits]
        session_context = [self._block_to_context_message(hit.block, heading="SESSION_MEMORY") for hit in session_hits]
        execution_messages = self._execution_messages(session_namespace)
        recent_messages = self._recent_messages(session_namespace)
        current_turn = [Message(role=MessageRole.USER, content=user_message)]
        zones = [
            ContextZone(name="stable_control", messages=project_control, stable=True, notes="Project-scoped durable control blocks."),
            ContextZone(name="project_sources", messages=source_messages, stable=True, notes="Explicit project control sources."),
            ContextZone(name="tool_manifest", messages=tool_messages, stable=True, notes="Stable tool manifest for the active runtime."),
            ContextZone(name="turn_control", messages=dynamic_control, stable=False, notes="Turn-scoped control hints such as skills and subagents."),
            ContextZone(name="derived_project_context", messages=derived_context, stable=False, notes="Derived project resources such as repo map and overview."),
            ContextZone(name="retrieved_project_memory", messages=durable_context, stable=False, notes="Promoted durable project memory hits."),
            ContextZone(name="retrieved_session_memory", messages=session_context, stable=False, notes="Current session and subagent memory hits."),
            ContextZone(name="execution_state", messages=execution_messages, stable=False, notes="Planner cursor, blocked steps, and open artifacts."),
            ContextZone(name="recent_turns", messages=recent_messages, stable=False, notes="Latest session transcript, including tool observations."),
            ContextZone(name="new_user_turn", messages=current_turn, stable=False, notes="Current user turn."),
        ]
        stable_prefix_hash = content_address([message.to_openai_dict() for zone in zones if zone.stable for message in zone.messages])
        return ContextAssembly(
            zones=zones,
            provider_hints={
                "stable_prefix_hash": stable_prefix_hash,
                "zone_order": [zone.name for zone in zones],
                "query": user_message,
            },
            diagnostics={
                "stable_prefix_tokens": sum(zone.approx_tokens() for zone in zones if zone.stable),
                "dynamic_tokens": sum(zone.approx_tokens() for zone in zones if not zone.stable),
                "project_block_ids": [hit.block.block_id for hit in durable_hits],
                "session_block_ids": [hit.block.block_id for hit in session_hits],
                "source_keys": [str(source["source_key"]) for source in sources],
                "derived_resources": [str(resource["resource_name"]) for resource in resources],
                "execution_state_keys": sorted((self.store.get_execution_state(session_namespace or "") or {}).keys()) if session_namespace else [],
            },
        )

    def _project_hits(self, query: str, *, top_k: int) -> list[RetrievalHit]:
        hits = self.retriever.retrieve(namespace=self.project_namespace, query=query, top_k=top_k)
        durable = []
        for hit in hits:
            if hit.block.plane == BlockPlane.CONTROL:
                continue
            if hit.block.kind.value not in self.options.durable_kinds:
                continue
            durable.append(hit)
        return durable[:6]

    def _session_hits(self, session_namespace: str | None, query: str, *, top_k: int) -> list[RetrievalHit]:
        if not session_namespace:
            return []
        hits = self.retriever.retrieve(namespace=session_namespace, query=query, top_k=top_k)
        return [hit for hit in hits if hit.block.plane != BlockPlane.CONTROL][:6]

    def _sorted_control_blocks(self, namespace: str) -> list[MemoryBlock]:
        priority = {
            BlockKind.POLICY: 0,
            BlockKind.TOOL_MANIFEST: 1,
            BlockKind.CONSTRAINT: 2,
            BlockKind.PREFERENCE: 3,
            BlockKind.STYLE: 4,
            BlockKind.FACT: 5,
            BlockKind.DECISION: 6,
        }
        blocks = [block for block in self.store.list_control_blocks(namespace) if block.active]
        return sorted(blocks, key=lambda block: (priority.get(block.kind, 99), -block.stability, block.address()))

    def _execution_messages(self, session_namespace: str | None) -> list[Message]:
        if not session_namespace:
            return []
        state = self.store.get_execution_state(session_namespace)
        if not state:
            return []
        lines: list[str] = []
        scalar_keys = ["objective", "current_step", "status", "blocked_reason"]
        for key in scalar_keys:
            if key in state and state[key]:
                lines.append(f"{key}: {state[key]}")
        list_keys = ["completed_steps", "blocked_steps", "active_todos", "open_artifacts"]
        for key in list_keys:
            raw_value = state.get(key)
            if not raw_value:
                continue
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError:
                parsed = raw_value
            if isinstance(parsed, list):
                lines.append(f"{key}: " + ", ".join(str(item) for item in parsed))
            else:
                lines.append(f"{key}: {parsed}")
        if "agent_state" in state:
            try:
                state_payload = json.loads(state["agent_state"])
            except json.JSONDecodeError:
                state_payload = {"raw": state["agent_state"]}
            frontier = [todo["content"] for todo in state_payload.get("todos", [])[:4] if todo.get("status") != "completed"]
            if frontier:
                lines.append("todo_frontier: " + " | ".join(frontier))
        if not lines:
            return []
        return [Message(role=MessageRole.USER, content="[EXECUTION_STATE]\n" + "\n".join(lines))]

    def _recent_messages(self, session_namespace: str | None) -> list[Message]:
        if not session_namespace:
            return []
        events = [
            event
            for event in self.store.list_events(session_namespace)
            if event.role not in {MessageRole.SYSTEM, MessageRole.DEVELOPER}
        ][-self.options.recent_turns :]
        return [Message(role=event.role, content=event.content, metadata=event.metadata) for event in events]

    def _record_candidate(self, block: MemoryBlock, *, session_namespace: str, event: EventRecord, source: str) -> None:
        if block.kind.value not in self.options.candidate_kinds:
            return
        if block.plane == BlockPlane.CONTROL:
            return
        normalized = self._candidate_key(block.kind.value, block.text)
        if not normalized:
            return
        candidate = self.store.record_memory_candidate(
            namespace=self.project_namespace,
            normalized_key=normalized,
            kind=block.kind.value,
            text=block.text,
            evidence={
                "event_id": event.event_id,
                "session_namespace": session_namespace,
                "source": source,
                "source_event_ids": list(block.source_event_ids),
            },
            salience=block.salience,
            stability=block.stability,
            confidence=block.confidence,
        )
        candidate = self._corroborate_candidate(candidate)
        if candidate["status"] != "pending":
            return
        if len(candidate["evidence"]) < self.options.candidate_min_evidence:
            return
        if float(candidate["stability"]) < self.options.promotion_min_stability:
            return
        if float(candidate["salience"]) < self.options.promotion_min_salience:
            return
        self.promote_candidate(int(candidate["candidate_id"]))

    def _merge_block(self, block: MemoryBlock) -> None:
        existing = self.store.list_blocks(block.namespace)
        target = None
        for prior in existing:
            if prior.plane == block.plane and prior.kind == block.kind and prior.text.lower() == block.text.lower():
                target = prior
                break
        if target is None:
            self.store.upsert_block(block)
            return
        if (block.salience + block.stability) >= (target.salience + target.stability):
            self.store.supersede_block(target.block_id, block)

    def _sync_project_source_blocks(self, sources: list[dict[str, object]]) -> None:
        live_keys: set[str] = set()
        for source in sources:
            whole_key = f"project_source:{source['source_key']}"
            live_keys.add(whole_key)
            self._sync_named_control_block(
                control_key=whole_key,
                kind=BlockKind.POLICY,
                text=f"[PROJECT_SOURCE:{source['source_path']}]\n{source['content']}",
                tags=["project_source", str(source["source_kind"])],
                metadata={
                    "source_key": str(source["source_key"]),
                    "source_kind": str(source["source_kind"]),
                    "content_hash": str(source["content_hash"]),
                },
            )
            for fragment in self._extract_source_fragments(source):
                live_keys.add(str(fragment["control_key"]))
                self._sync_named_control_block(
                    control_key=str(fragment["control_key"]),
                    kind=BlockKind(str(fragment["kind"])),
                    text=str(fragment["text"]),
                    tags=["project_source_fragment", str(source["source_kind"]), str(fragment["kind"])],
                    metadata={
                        "source_key": str(source["source_key"]),
                        "source_kind": str(source["source_kind"]),
                        "fragment_type": str(fragment["fragment_type"]),
                        "fragment_label": str(fragment["fragment_label"]),
                        "fragment_line": int(fragment["fragment_line"]),
                        "content_hash": str(source["content_hash"]),
                    },
                )
        removed = self._deactivate_stale_source_control_blocks(live_keys)
        self._last_source_control_keys = sorted(live_keys)
        self._last_stale_source_blocks_removed = removed

    def _deactivate_stale_source_control_blocks(self, live_keys: set[str]) -> int:
        removed = 0
        for block in self.store.list_blocks(self.project_namespace, active_only=False):
            if not block.active:
                continue
            control_key = str(block.metadata.get("control_key", ""))
            if not control_key.startswith(("project_source:", "project_source_fragment:")):
                continue
            if control_key in live_keys:
                continue
            self.store.deactivate_block(block.block_id)
            removed += 1
        return removed

    def _sync_named_control_block(
        self,
        *,
        control_key: str,
        kind: BlockKind,
        text: str,
        tags: list[str],
        metadata: dict[str, object],
    ) -> None:
        existing = [
            block
            for block in self.store.list_blocks(self.project_namespace, active_only=False)
            if block.metadata.get("control_key") == control_key and block.active
        ]
        block = MemoryBlock(
            namespace=self.project_namespace,
            plane=BlockPlane.CONTROL,
            kind=kind,
            text=text,
            salience=0.92,
            stability=0.98,
            confidence=0.95,
            tags=tags,
            metadata={"control_key": control_key, **metadata},
        )
        if not existing:
            self.store.upsert_block(block)
            return
        current = existing[0]
        if current.text == text and current.kind == kind:
            return
        self.store.supersede_block(current.block_id, block)

    def _extract_source_fragments(self, source: dict[str, object]) -> list[dict[str, object]]:
        content = str(source["content"])
        source_key = str(source["source_key"])
        fragments: dict[str, dict[str, object]] = {}
        for index, line in enumerate(content.splitlines(), start=1):
            match = re.match(r"^\s*(Preference|Style|Constraint|Decision)\s*:\s*(.+?)\s*$", line)
            if not match:
                continue
            kind_name = match.group(1).lower()
            text = match.group(2).strip()
            control_key = f"project_source_fragment:{source_key}:{kind_name}:line-{index}"
            fragments[control_key] = {
                "control_key": control_key,
                "kind": kind_name,
                "text": text,
                "fragment_type": "line",
                "fragment_label": match.group(1),
                "fragment_line": index,
            }

        lines = content.splitlines()
        heading_pattern = re.compile(r"^\s{0,3}(#{1,6})\s+(Preference|Style|Constraint|Decision)s?\s*$", re.IGNORECASE)
        for index, line in enumerate(lines, start=1):
            heading = heading_pattern.match(line)
            if not heading:
                continue
            kind_name = heading.group(2).lower()
            body_lines: list[str] = []
            cursor = index
            while cursor < len(lines):
                next_line = lines[cursor]
                if re.match(r"^\s{0,3}#{1,6}\s+", next_line):
                    break
                body_lines.append(next_line)
                cursor += 1
            text = "\n".join(item.strip() for item in body_lines if item.strip()).strip()
            if not text:
                continue
            control_key = f"project_source_fragment:{source_key}:{kind_name}:heading-{index}"
            fragments[control_key] = {
                "control_key": control_key,
                "kind": kind_name,
                "text": text,
                "fragment_type": "heading",
                "fragment_label": heading.group(2),
                "fragment_line": index,
            }
        return [fragments[key] for key in sorted(fragments)]

    def _corroborate_pending_candidates(
        self,
        *,
        sources: list[dict[str, object]],
        resources: list[dict[str, object]],
    ) -> None:
        pending = self.store.list_memory_candidates(self.project_namespace, status="pending")
        for candidate in pending:
            self._corroborate_candidate(candidate, sources=sources, resources=resources)

    def _corroborate_candidate(
        self,
        candidate: dict[str, object],
        *,
        sources: list[dict[str, object]] | None = None,
        resources: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        sources = sources if sources is not None else self.store.list_memory_sources(self.project_namespace)
        resources = resources if resources is not None else self.store.list_derived_project_resources(self.project_namespace)
        normalized_terms = normalize_terms(str(candidate["text"]))
        if not normalized_terms:
            return candidate
        for source in sources:
            if self._content_supports_terms(str(source["content"]), normalized_terms):
                candidate = self.store.record_memory_candidate(
                    namespace=self.project_namespace,
                    normalized_key=str(candidate["normalized_key"]),
                    kind=str(candidate["kind"]),
                    text=str(candidate["text"]),
                    evidence={
                        "source": "project_source",
                        "source_ref": str(source["source_key"]),
                        "source_key": str(source["source_key"]),
                        "source_path": str(source["source_path"]),
                        "content_hash": str(source["content_hash"]),
                    },
                    salience=float(candidate["salience"]),
                    stability=max(float(candidate["stability"]), 0.85),
                    confidence=max(float(candidate["confidence"]), 0.85),
                )
        for resource in resources:
            if self._content_supports_terms(str(resource["content"]), normalized_terms):
                candidate = self.store.record_memory_candidate(
                    namespace=self.project_namespace,
                    normalized_key=str(candidate["normalized_key"]),
                    kind=str(candidate["kind"]),
                    text=str(candidate["text"]),
                    evidence={
                        "source": "derived_resource",
                        "source_ref": str(resource["resource_name"]),
                        "resource_name": str(resource["resource_name"]),
                        "content_hash": str(resource["content_hash"]),
                    },
                    salience=float(candidate["salience"]),
                    stability=max(float(candidate["stability"]), 0.82),
                    confidence=max(float(candidate["confidence"]), 0.82),
                )
        return candidate

    def _scan_project_sources(self) -> list[dict[str, object]]:
        paths: dict[str, Path] = {}
        for pattern in self.options.explicit_source_patterns:
            for path in self.workspace_root.glob(pattern):
                if path.is_file():
                    paths[str(path.relative_to(self.workspace_root))] = path
        if self.options.import_continue_rules:
            for path in self.workspace_root.glob(".continue/rules/**/*.md"):
                if path.is_file():
                    paths[str(path.relative_to(self.workspace_root))] = path
        if self.options.import_openhands_microagents:
            for path in self.workspace_root.glob(".openhands/microagents/**/*.md"):
                if path.is_file():
                    paths[str(path.relative_to(self.workspace_root))] = path
        sources: list[dict[str, object]] = []
        for rel_path, path in sorted(paths.items()):
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            source_kind = "project_source"
            if rel_path.startswith(".continue/"):
                source_kind = "continue_rule"
            elif rel_path.startswith(".openhands/"):
                source_kind = "openhands_microagent"
            elif rel_path == "AGENTS.md":
                source_kind = "agents_md"
            elif rel_path == "CLAUDE.md":
                source_kind = "claude_md"
            sources.append(
                {
                    "source_key": rel_path,
                    "source_path": rel_path,
                    "source_kind": source_kind,
                    "content": content,
                    "content_hash": sha1(content.encode("utf-8")).hexdigest(),
                    "metadata": {"mtime_ns": path.stat().st_mtime_ns},
                }
            )
        return sources

    def _derive_project_resources(self) -> list[dict[str, object]]:
        resources: list[dict[str, object]] = []
        if self.options.derive_repo_map:
            repo_map = self._build_repo_map()
            resources.append(
                {
                    "resource_name": "repo_map",
                    "content": repo_map,
                    "content_hash": sha1(repo_map.encode("utf-8")).hexdigest(),
                    "metadata": {"generator": "nanocli.repo_map"},
                }
            )
        if self.options.derive_repo_overview:
            repo_overview = self._build_repo_overview()
            resources.append(
                {
                    "resource_name": "repo_overview",
                    "content": repo_overview,
                    "content_hash": sha1(repo_overview.encode("utf-8")).hexdigest(),
                    "metadata": {"generator": "nanocli.repo_overview"},
                }
            )
        return resources

    def _build_repo_map(self) -> str:
        entries: list[str] = []
        for path in sorted(self.workspace_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.workspace_root)
            if self._ignore_repo_path(relative):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            symbols = self._extract_symbols(path, text)
            if symbols:
                entries.append(f"{relative}: {', '.join(symbols[:8])}")
            else:
                entries.append(f"{relative}")
            if len(entries) >= 160:
                break
        return "[REPO_MAP]\n" + "\n".join(entries)

    def _build_repo_overview(self) -> str:
        lines: list[str] = []
        top_level = [path.name for path in sorted(self.workspace_root.iterdir()) if not self._ignore_repo_path(Path(path.name))]
        lines.append("top_level: " + ", ".join(top_level[:24]))
        for candidate in ["README.md", "pyproject.toml", "package.json"]:
            path = self.workspace_root / candidate
            if path.exists() and path.is_file():
                content = path.read_text(encoding="utf-8").strip()
                preview = "\n".join(line for line in content.splitlines()[:12] if line.strip())
                lines.append(f"[{candidate}]\n{preview}")
        workflow_dir = self.workspace_root / ".github" / "workflows"
        if workflow_dir.exists():
            workflow_names = [str(path.relative_to(self.workspace_root)) for path in sorted(workflow_dir.glob("*")) if path.is_file()]
            if workflow_names:
                lines.append("workflows: " + ", ".join(workflow_names[:12]))
        return "[REPO_OVERVIEW]\n" + "\n\n".join(lines)

    @staticmethod
    def _extract_symbols(path: Path, text: str) -> list[str]:
        suffix = path.suffix.lower()
        symbols: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if suffix == ".py":
                if stripped.startswith("class "):
                    symbols.append(stripped.split("class ", 1)[1].split("(", 1)[0].split(":", 1)[0].strip())
                elif stripped.startswith("def "):
                    symbols.append(stripped.split("def ", 1)[1].split("(", 1)[0].strip())
            elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
                if stripped.startswith("export function ") or stripped.startswith("function "):
                    symbols.append(stripped.split("function ", 1)[1].split("(", 1)[0].strip())
                elif stripped.startswith("export class ") or stripped.startswith("class "):
                    symbols.append(stripped.split("class ", 1)[1].split("{", 1)[0].strip())
        return symbols

    @staticmethod
    def _candidate_key(kind: str, text: str) -> str:
        normalized = normalize_terms(text)
        if not normalized:
            return ""
        return f"{kind}:" + " ".join(normalized[:48])

    @staticmethod
    def _tool_manifest_text(tools: list[ToolSchema]) -> str:
        lines = [f"- {tool.name}: {tool.description} (schema_hash={tool.stable_hash()})" for tool in tools]
        return "[STABLE_TOOL_MANIFEST]\n" + "\n".join(lines)

    @staticmethod
    def _native_manifest_tools(extra: dict[str, object]) -> list[ToolSchema]:
        manifest: list[ToolSchema] = []
        for item in extra.get("native_mcp_tools", []) or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("server_label") or "mcp")
            manifest.append(
                ToolSchema(
                    name=f"mcp::{label}",
                    description=f"Native MCP server {label} at {item.get('server_url', '')}".strip(),
                    parameters_json_schema={"type": "object", "properties": {}, "additionalProperties": True},
                )
            )
        for item in extra.get("anthropic_mcp_servers", []) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "mcp")
            manifest.append(
                ToolSchema(
                    name=f"mcp::{name}",
                    description=f"Native MCP server {name} at {item.get('url', '')}".strip(),
                    parameters_json_schema={"type": "object", "properties": {}, "additionalProperties": True},
                )
            )
        return manifest

    @staticmethod
    def _block_to_system_message(block: MemoryBlock) -> Message:
        return Message(
            role=MessageRole.SYSTEM,
            content=f"[{block.kind.value.upper()}|{block.plane.value}] {block.text}",
            metadata={"block_id": block.block_id, "block_kind": block.kind.value, "block_plane": block.plane.value},
        )

    @staticmethod
    def _block_to_context_message(block: MemoryBlock, *, heading: str) -> Message:
        return Message(
            role=MessageRole.USER,
            content=f"[{heading}] [{block.kind.value}/{block.plane.value}] {block.text}",
            metadata={"block_id": block.block_id, "context_heading": heading},
        )

    @staticmethod
    def _project_source_message(source: dict[str, object]) -> Message:
        return Message(
            role=MessageRole.SYSTEM,
            content=f"[PROJECT_SOURCE:{source['source_path']}]\n{source['content']}",
            metadata={"source_key": source["source_key"], "source_kind": source["source_kind"]},
        )

    @staticmethod
    def _project_sources_summary_message(sources: list[dict[str, object]]) -> Message:
        items = [f"- {source['source_path']} ({source['source_kind']})" for source in sources]
        return Message(role=MessageRole.SYSTEM, content="[PROJECT_SOURCES]\n" + "\n".join(items))

    @staticmethod
    def _project_resource_message(resource: dict[str, object]) -> Message:
        return Message(
            role=MessageRole.USER,
            content=f"[PROJECT_RESOURCE:{resource['resource_name']}]\n{resource['content']}",
            metadata={"resource_name": resource["resource_name"]},
        )

    @staticmethod
    def _content_supports_terms(content: str, terms: list[str]) -> bool:
        normalized = set(normalize_terms(content))
        if not normalized:
            return False
        required = set(terms[: min(8, len(terms))])
        return len(required & normalized) >= max(2, min(len(required), 3))

    def _ignore_repo_path(self, relative: Path) -> bool:
        parts = relative.parts
        if any(part in IGNORED_DIRS for part in parts):
            return True
        relative_str = relative.as_posix()
        if any(marker in relative_str for marker in IGNORED_PATH_MARKERS):
            return True
        if relative.name.endswith((".db", ".sqlite", ".sqlite3", ".pyc")):
            return True
        return False

    @staticmethod
    def _hit_payload(hit: RetrievalHit) -> dict[str, object]:
        return {
            "block_id": hit.block.block_id,
            "plane": hit.block.plane.value,
            "kind": hit.block.kind.value,
            "score": round(hit.score, 4),
            "channels": {key: round(value, 4) for key, value in hit.channel_scores.items()},
        }
