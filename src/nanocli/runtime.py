from __future__ import annotations

from hashlib import sha1
from pathlib import Path
from typing import Any
from dataclasses import dataclass
import json
import os

from agent_memory_os import ClaudeCodeMemoryExporter, Message, MessageRole
from agent_memory_os.models import ProviderRequest, ToolSchema
from agent_memory_os.providers import AnthropicRuntime, OpenAICompatibleRuntime, OpenAIRuntime
from plan_todo_agent.core.interfaces import BaseProviderAdapter
from plan_todo_agent.core.schemas import Plan, PlanStep, StepKind, TodoItem, TodoStatus
from plan_todo_agent.planning.critic import HeuristicPlanCritic
from plan_todo_agent.planning.engine import AgentState, DualLayerPlanTodoAgent
from plan_todo_agent.providers.anthropic_like import AnthropicMessagesAdapter as PlanAnthropicMessagesAdapter
from plan_todo_agent.providers.openai_chat_like import OpenAIChatLikeAdapter
from plan_todo_agent.providers.openai_responses import OpenAIResponsesAdapter as PlanOpenAIResponsesAdapter
from plan_todo_agent.renderers.chatgpt import ChatGPTRenderer
from plan_todo_agent.renderers.claude_code import ClaudeCodeRenderer
from plan_todo_agent.skills.repository_refactor import RepositoryRefactorSkill
from progressive_disclosure import ProgressiveDisclosureManager
from progressive_disclosure.domain import ActionKind, ActionRecord, AgentPhase, DisclosureContext, DisclosurePreferences, TaskRisk, TaskStateSnapshot
from progressive_disclosure.events import AgentEvent, EventKind

from .config import load_config
from .mcp_client import AsyncRuntimeMcpServer, McpClientManager, provider_supports_native_mcp, resolve_mcp_integration_mode
from .memory_runtime import CompositeMemoryRuntime
from .models import LoadedSkill, McpServerConfig, ModelProfile, RunResult, RunStatus, SessionSummary, SubagentRunSummary, TraceKind
from .provider_loop import ProviderToolLoop, ToolCall, ToolExecution
from .skills_runtime import SkillManager, available_render_targets
from .sqlite_memory import SQLiteEventStore
from .storage import LocalStateStore
from .subagents_runtime import SubagentManager
from .tools import MountedMcpServer, build_builtin_tool_catalog


class _NoopPlanProvider(BaseProviderAdapter):
    name = "noop"

    def build_request(self, *, system_prompt: str, user_prompt: str, tools: list[Any], turn: Any = None) -> dict[str, Any]:
        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "tools": [tool.name for tool in tools],
            "turn": turn.to_dict() if turn else None,
        }

    def parse_response(self, response: dict[str, Any]) -> dict[str, Any]:
        return response

    def format_capabilities(self) -> dict[str, Any]:
        return {"mode": "noop"}


@dataclass(slots=True)
class McpRuntimePlan:
    native_servers: list[McpServerConfig]
    mounted_servers: list[MountedMcpServer]


class AgentRuntime:
    def __init__(self, cwd: Path | None = None, config_path: Path | None = None) -> None:
        self.cwd = (cwd or Path.cwd()).resolve()
        self.config = load_config(self.cwd, config_path)
        if self.config.paths is None:
            raise RuntimeError("config paths were not resolved")
        self.paths = self.config.paths
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        self.paths.project_dir.mkdir(parents=True, exist_ok=True)
        self.store = LocalStateStore(self.paths.db_path, self.paths.artifacts_dir)
        self.memory_store = SQLiteEventStore(self.paths.db_path)
        self.memory = CompositeMemoryRuntime(
            store=self.memory_store,
            project_namespace=self._project_namespace(),
            options=self.config.memory,
            workspace_root=self.cwd,
        )
        self.memory.ensure_project_control(
            system_policies=[
                "You are nanocli, a local production-minded coding agent.",
                "Preserve user constraints, keep diffs minimal, and verify before declaring success.",
                "Prefer a stable cache-safe prefix and structured trace capture.",
                *self.config.system_policies,
            ],
            user_instructions=self.config.user_instructions,
        )
        self.disclosure = ProgressiveDisclosureManager()
        self.skills = SkillManager(self.cwd, self.config.skills)
        self.mcp = McpClientManager(store=self.store, workspace_root=self.cwd)
        self.subagents = (
            SubagentManager(
                max_parallel_agents=self.config.subagents.max_parallel_agents,
                timeout_seconds=self.config.subagents.timeout_seconds,
            )
            if self.config.subagents.enabled
            else None
        )
        self.plan_skill = self._resolve_planner_skill()
        self.critic = HeuristicPlanCritic()

    def resolve_profile(self, name: str | None = None) -> ModelProfile:
        profile_name = name or self.config.default_profile
        if profile_name not in self.config.profiles:
            raise KeyError(f"Unknown profile: {profile_name}")
        return self.config.profiles[profile_name]

    def create_session(self, *, title: str | None = None, profile_name: str | None = None) -> SessionSummary:
        profile = self.resolve_profile(profile_name)
        session_title = title or "Untitled session"
        session_id = self.store.create_session(title=session_title, profile=profile.name, cwd=self.cwd)
        session_namespace = self._session_namespace(session_id)
        self._persist_agent_state(
            session_namespace,
            self._bootstrap_state("Untitled session"),
            status="idle",
            objective="Untitled session",
        )
        return self.store.get_session(session_id)

    def chat_turn(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        profile_name: str | None = None,
        debug: bool = False,
        execute: bool = True,
        allow_web: bool = False,
        selected_skills: list[str] | None = None,
        use_subagents: bool | None = None,
    ) -> RunResult:
        if session_id is None:
            created = self.create_session(
                title=self._title_from_prompt(prompt) if self.config.chat.auto_title_from_first_message else "Untitled session",
                profile_name=profile_name or self.config.chat.default_repl_profile or self.config.default_profile,
            )
            session_id = created.session_id
        return self.run(
            prompt,
            profile_name=profile_name,
            debug=debug,
            execute=execute,
            allow_web=allow_web,
            session_id=session_id,
            selected_skills=selected_skills,
            use_subagents=use_subagents,
        )

    def run(
        self,
        objective: str,
        *,
        profile_name: str | None = None,
        debug: bool = False,
        execute: bool = True,
        allow_web: bool = False,
        session_id: str | None = None,
        selected_skills: list[str] | None = None,
        use_subagents: bool | None = None,
    ) -> RunResult:
        session = self.store.get_session(session_id) if session_id else None
        profile = self.resolve_profile(profile_name or (session.profile if session else None))
        loaded_skills = self.skills.load_selected(selected_skills)
        extra_tools = self.skills.build_runtime_tools(loaded_skills)
        run_summary = self.store.create_run(objective=objective, profile=profile.name, cwd=self.cwd, session_id=session_id)
        session_namespace = self._session_namespace(session_id) if session_id else self._run_namespace(run_summary.run_id)
        self.mcp.bind_context(run_id=run_summary.run_id, session_id=session_id)
        mcp_plan = self._resolve_mcp_runtime_plan(profile)
        catalog = build_builtin_tool_catalog(
            workspace_root=self.cwd,
            run_id=run_summary.run_id,
            session_id=session_id,
            allow_web=allow_web,
            mounted_mcp_servers=mcp_plan.mounted_servers,
            mcp_manager=self.mcp,
            extra_tools=extra_tools,
            tool_options=self.config.tools,
        )
        for note in catalog.notes:
            self.store.append_trace(run_summary.run_id, kind=TraceKind.NOTE, message=note, payload={})

        current_state = self._load_agent_state(session_namespace)
        if current_state is None or current_state.objective == "Untitled session":
            state = self._bootstrap_state(objective)
        else:
            state = self._planning_agent().apply_execution_feedback(current_state, observations=[f"user_turn: {objective}"])
        self._validate_plan(state)
        self._persist_agent_state(session_namespace, state, status="planning", objective=state.objective)
        plan_json = state.plan.to_pretty_json()
        plan_artifact = self.store.save_artifact(run_summary.run_id, "plan", json.loads(plan_json))
        self.store.append_trace(
            run_summary.run_id,
            kind=TraceKind.PLAN,
            message="planner state persisted",
            payload={"todo_count": len(state.todos), "completed_steps": list(state.completed_steps)},
            artifact_path=plan_artifact,
        )
        self.store.update_run(run_summary.run_id, status=RunStatus.PLANNED, phase="planning")

        self.memory.observe_session_message(session_namespace, Message(role=MessageRole.USER, content=objective), source="conversation")
        if session_id:
            self.store.append_session_message(session_id, role="user", content=objective, run_id=run_summary.run_id)
            self.store.append_session_event(
                session_id,
                name="turn_started",
                payload={"objective": objective, "profile": profile.name},
                run_id=run_summary.run_id,
            )

        if loaded_skills:
            self.store.append_trace(
                run_summary.run_id,
                kind=TraceKind.NOTE,
                message="loaded runtime skills",
                payload={"skills": [skill.name for skill in loaded_skills]},
            )

        disclosures: list[str] = []
        disclosures.extend(self._emit_disclosure(run_summary.run_id, state, EventKind.TASK_STARTED, objective, session_id=session_id))
        disclosures.extend(self._emit_disclosure(run_summary.run_id, state, EventKind.PLAN_CREATED, objective, session_id=session_id))

        subagent_summary: SubagentRunSummary | None = None
        should_delegate = use_subagents if use_subagents is not None else bool(self.subagents and self.config.experimental.subagents)
        if self.subagents and should_delegate and self.subagents.should_delegate(objective, self.config.subagents.auto_delegate_keywords):
            subagent_payload = self.subagents.run(
                task_id=run_summary.run_id,
                query=objective,
                shared_context={"cwd": str(self.cwd), "session_id": session_id or ""},
            )
            self._persist_subagent_payload(run_summary.run_id, session_id=session_id, payload=subagent_payload)
            subagent_summary = self.subagents.summarize(run_summary.run_id, subagent_payload)
            subagent_artifact = self.store.save_artifact(run_summary.run_id, "subagents", subagent_payload)
            self.store.append_trace(
                run_summary.run_id,
                kind=TraceKind.NOTE,
                message="completed subagent delegation",
                payload={
                    "selected_agents": subagent_summary.selected_agents,
                    "trace_count": len(subagent_summary.traces),
                },
                artifact_path=subagent_artifact,
            )
            if session_id:
                self.store.append_session_event(
                    session_id,
                    name="subagents_completed",
                    payload={
                        "selected_agents": subagent_summary.selected_agents,
                        "merged": subagent_summary.merged,
                    },
                    run_id=run_summary.run_id,
                )

        control_messages = self._runtime_control_messages(loaded_skills, subagent_summary)
        provider_request, memory_snapshot = self.memory.prepare_request(
            provider_name=profile.provider,
            model=profile.model,
            user_message=objective,
            tools=catalog.tool_schemas,
            session_namespace=session_namespace,
            extra=self._provider_extra(profile, native_mcp_servers=mcp_plan.native_servers),
            control_messages=control_messages,
        )
        if loaded_skills:
            provider_request.diagnostics["skills"] = [skill.name for skill in loaded_skills]
        if subagent_summary:
            provider_request.diagnostics["subagents"] = list(subagent_summary.selected_agents)
        if self.config.mcp_servers:
            provider_request.diagnostics["mcp"] = {
                "native": [server.name for server in mcp_plan.native_servers],
                "mounted": [
                    {"server": mounted.name, "mode": mounted.mode}
                    for mounted in mcp_plan.mounted_servers
                ],
            }
        request_payload = self._provider_request_dict(provider_request)
        request_artifact = self.store.save_artifact(run_summary.run_id, "provider_request", request_payload)
        self.store.append_trace(
            run_summary.run_id,
            kind=TraceKind.PROVIDER_REQUEST,
            message=f"compiled provider request for profile {profile.name}",
            payload={"provider": profile.provider, "model": profile.model, "tool_mode": profile.tool_mode},
            artifact_path=request_artifact,
        )

        project_snapshot = self.memory.export_namespace_state(self._project_namespace())
        project_artifact = self.store.save_artifact(run_summary.run_id, "project_memory_export", project_snapshot)
        self.store.append_memory_snapshot(
            run_summary.run_id,
            session_id=session_id,
            namespace=project_snapshot["namespace"],
            event_count=len(project_snapshot["events"]),
            block_count=len(project_snapshot["blocks"]),
            artifact_path=project_artifact,
        )
        session_snapshot = self.memory.export_namespace_state(session_namespace)
        session_artifact = self.store.save_artifact(run_summary.run_id, "session_memory_export", session_snapshot)
        self.store.append_memory_snapshot(
            run_summary.run_id,
            session_id=session_id,
            namespace=session_snapshot["namespace"],
            event_count=len(session_snapshot["events"]),
            block_count=len(session_snapshot["blocks"]),
            artifact_path=session_artifact,
        )

        memory_export_path = self._persist_project_memory(project_snapshot)
        claude_export = self._export_claude_memory(run_summary.run_id)
        self.store.append_trace(
            run_summary.run_id,
            kind=TraceKind.MEMORY,
            message="composite memory compiled and persisted",
            payload={
                "project_events": len(project_snapshot["events"]),
                "project_blocks": len(project_snapshot["blocks"]),
                "session_events": len(session_snapshot["events"]),
                "session_blocks": len(session_snapshot["blocks"]),
                "project_memory": str(memory_export_path),
                "claude_export": claude_export,
                "tool_audit": str(catalog.audit_path),
                "zone_order": memory_snapshot.assembly.provider_hints["zone_order"],
            },
            artifact_path=project_artifact,
        )

        provider_response: dict[str, Any] | None = None
        status = RunStatus.COMPILED
        summary_text = "compiled provider request without remote execution"

        try:
            if execute:
                api_key = os.getenv(profile.api_key_env)
                if not api_key:
                    raise RuntimeError(f"Missing API key env var: {profile.api_key_env}")
                disclosures.extend(self._emit_disclosure(run_summary.run_id, state, EventKind.ACTION_STARTED, objective, session_id=session_id, action_target=profile.provider))
                if profile.tool_mode == "auto":
                    loop = ProviderToolLoop(
                        profile=profile,
                        run_id=run_summary.run_id,
                        session_id=session_id,
                        store=self.store,
                        invoke_provider=self._invoke_provider,
                        tool_registry=catalog.registry,
                        memory=self.memory,
                        on_tool_observation=lambda tool_call, execution, observation: self._record_tool_observation(
                            session_id=session_id,
                            session_namespace=session_namespace,
                            run_id=run_summary.run_id,
                            tool_call=tool_call,
                            execution=execution,
                            observation=observation,
                        ),
                    )
                    loop_result = loop.run(provider_request, api_key=api_key)
                    provider_response = loop_result.response
                    response_text = loop_result.final_text
                else:
                    raw_response = self._invoke_provider(provider_request, profile, api_key)
                    provider_response = self._coerce_json(raw_response)
                    response_text = self._extract_response_text(provider_response)
                    response_artifact = self.store.save_artifact(run_summary.run_id, "provider_response", provider_response)
                    self.store.append_trace(
                        run_summary.run_id,
                        kind=TraceKind.PROVIDER_RESPONSE,
                        message="received provider response",
                        payload={"provider": profile.provider},
                        artifact_path=response_artifact,
                    )
                    self.store.append_provider_call(
                        run_summary.run_id,
                        session_id=session_id,
                        provider=provider_request.provider.value,
                        model=profile.model,
                        endpoint_style=provider_request.endpoint_style,
                        status="completed",
                        request_artifact_path=request_artifact,
                        response_artifact_path=response_artifact,
                        summary=(response_text or "provider call completed")[:500],
                    )
                if response_text:
                    self.memory.observe_session_message(session_namespace, Message(role=MessageRole.ASSISTANT, content=response_text), source="conversation")
                state = self._planning_agent().apply_execution_feedback(state, observations=[response_text[:500]] if response_text else [])
                self._persist_agent_state(session_namespace, state, status="active", objective=state.objective)
                latest_session_snapshot = self.memory.export_namespace_state(session_namespace)
                latest_memory_artifact = self.store.save_artifact(run_summary.run_id, "session_memory_post_response", latest_session_snapshot)
                self.store.append_memory_snapshot(
                    run_summary.run_id,
                    session_id=session_id,
                    namespace=latest_session_snapshot["namespace"],
                    event_count=len(latest_session_snapshot["events"]),
                    block_count=len(latest_session_snapshot["blocks"]),
                    artifact_path=latest_memory_artifact,
                )
                disclosures.extend(self._emit_disclosure(run_summary.run_id, state, EventKind.ACTION_COMPLETED, objective, session_id=session_id, action_target=profile.provider))
                summary_text = response_text or "provider call completed"
                status = RunStatus.COMPLETED

            disclosures.extend(self._emit_disclosure(run_summary.run_id, state, EventKind.TASK_COMPLETED, objective, session_id=session_id))
            run_summary = self.store.update_run(
                run_summary.run_id,
                status=status,
                phase="complete",
                summary=summary_text[:500],
            )
            if session_id:
                self._record_session_completion(
                    session_id,
                    run_id=run_summary.run_id,
                    profile=profile.name,
                    content=summary_text,
                    status="active",
                )
        except Exception as exc:
            error_artifact = None
            if debug:
                error_artifact = self.store.save_artifact(run_summary.run_id, "error", {"error": str(exc)})
            self.store.append_trace(
                run_summary.run_id,
                kind=TraceKind.EVENT,
                message="run failed",
                payload={"error": str(exc)},
                artifact_path=error_artifact,
            )
            disclosures.extend(self._emit_disclosure(run_summary.run_id, state, EventKind.ERROR, objective, session_id=session_id, error=str(exc)))
            self._persist_agent_state(session_namespace, state, status="error", objective=state.objective, blocked_reason=str(exc))
            run_summary = self.store.update_run(
                run_summary.run_id,
                status=RunStatus.FAILED,
                phase="recovery",
                summary=str(exc),
                error=str(exc),
            )
            if session_id:
                self.store.append_session_event(session_id, name="turn_failed", payload={"error": str(exc)}, run_id=run_summary.run_id)
                self.store.update_session(session_id, profile=profile.name, last_run_id=run_summary.run_id, status="error")
        traces = self.store.list_traces(run_summary.run_id)
        return RunResult(
            summary=run_summary,
            traces=traces,
            plan_json=plan_json,
            todo_items=[todo.to_dict() for todo in state.todos],
            memory_export=session_snapshot,
            provider_request=request_payload,
            provider_response=provider_response,
            disclosures=disclosures,
            session_id=session_id,
            subagent_summary=subagent_summary,
        )

    def list_runs(self, limit: int = 20):
        return self.store.list_runs(limit=limit)

    def get_run(self, run_id: str):
        return self.store.get_run(run_id)

    def get_traces(self, run_id: str):
        return self.store.list_traces(run_id)

    def list_sessions(self, limit: int = 50) -> list[SessionSummary]:
        return self.store.list_sessions(limit=limit)

    def get_session(self, session_id: str) -> SessionSummary:
        return self.store.get_session(session_id)

    def get_session_messages(self, session_id: str, limit: int = 200):
        return self.store.list_session_messages(session_id, limit=limit)

    def get_session_events(self, session_id: str, limit: int = 200):
        return self.store.list_session_events(session_id, limit=limit)

    def list_available_skills(self) -> list[LoadedSkill]:
        return list(self.skills.discover().values())

    def render_skills(
        self,
        *,
        names: list[str] | None = None,
        targets: list[str] | None = None,
        out_dir: Path | None = None,
    ) -> list[Path]:
        return self.skills.render(names=names, targets=targets, out_dir=out_dir)

    def install_skill(self, source: str, destination_root: Path | None = None) -> Path:
        return self.skills.install(source, destination_root)

    def available_skill_targets(self) -> list[str]:
        return available_render_targets()

    def list_subagents(self) -> list[dict[str, Any]]:
        if not self.subagents:
            return []
        return self.subagents.available_agents()

    def run_subagents(self, query: str, *, run_id: str | None = None) -> dict[str, Any]:
        if not self.subagents:
            raise RuntimeError("subagents are disabled in config")
        task_id = run_id or sha1(query.encode("utf-8")).hexdigest()[:16]
        return self.subagents.run(task_id=task_id, query=query, shared_context={"cwd": str(self.cwd)})

    def export_subagent_artifacts(self, run_id: str, *, provider: str | None = None) -> list[dict[str, Any]]:
        artifacts = self.store.list_subagent_provider_artifacts(run_id)
        if provider is None:
            return artifacts
        return [artifact for artifact in artifacts if artifact["provider"] == provider]

    def list_subagent_runs(self, run_id: str) -> list[dict[str, Any]]:
        return self.store.list_subagent_runs(run_id)

    def read_project_memory_snapshot(self) -> dict[str, Any]:
        return self.memory.export_namespace_state(self._project_namespace())

    def read_session_memory_snapshot(self, session_id: str) -> dict[str, Any]:
        return self.memory.export_namespace_state(self._session_namespace(session_id))

    def list_project_memory_sources(self) -> list[dict[str, Any]]:
        return self.memory.list_project_sources()

    def list_project_memory_resources(self) -> list[dict[str, Any]]:
        return self.memory.list_project_resources()

    def list_project_memory_candidates(self, *, status: str | None = None) -> list[dict[str, Any]]:
        return self.memory.list_memory_candidates(status=status)

    def promote_project_memory_candidate(self, candidate_id: int) -> dict[str, Any]:
        return self.memory.promote_candidate(candidate_id, manual=True)

    def reject_project_memory_candidate(self, candidate_id: int) -> dict[str, Any]:
        return self.memory.reject_candidate(candidate_id)

    def rebuild_project_memory(self) -> dict[str, Any]:
        self.memory.refresh_project_context()
        return self.read_project_memory_snapshot()

    def list_mcp_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.list_mcp_sessions(limit=limit)

    def list_mcp_messages(self, mcp_session_id: int, limit: int = 200) -> list[dict[str, Any]]:
        return self.store.list_mcp_messages(mcp_session_id, limit=limit)

    def list_mcp_stream_events(self, mcp_session_id: int, limit: int = 200) -> list[dict[str, Any]]:
        return self.store.list_mcp_stream_events(mcp_session_id, limit=limit)

    def get_plan_state(self, session_id: str) -> dict[str, Any]:
        state = self._load_agent_state(self._session_namespace(session_id))
        if state is None:
            raise KeyError(f"No planner state found for session {session_id}")
        return self._serialize_agent_state(state)

    def mark_step_done(self, session_id: str, step_id: str) -> dict[str, Any]:
        namespace = self._session_namespace(session_id)
        state = self._load_agent_state(namespace)
        if state is None:
            raise KeyError(f"No planner state found for session {session_id}")
        updated = self._planning_agent().apply_execution_feedback(state, completed_step_ids=[step_id], observations=[f"completed {step_id}"])
        self._persist_agent_state(namespace, updated, status="active", objective=updated.objective)
        self.store.append_session_event(session_id, name="plan_step_completed", payload={"step_id": step_id})
        return self._serialize_agent_state(updated)

    def mark_step_blocked(self, session_id: str, step_id: str, reason: str | None = None) -> dict[str, Any]:
        namespace = self._session_namespace(session_id)
        state = self._load_agent_state(namespace)
        if state is None:
            raise KeyError(f"No planner state found for session {session_id}")
        observations = [f"blocked {step_id}"] + ([reason] if reason else [])
        updated = self._planning_agent().apply_execution_feedback(state, blocked_step_ids=[step_id], observations=observations)
        self._persist_agent_state(namespace, updated, status="blocked", objective=updated.objective, blocked_reason=reason)
        self.store.append_session_event(session_id, name="plan_step_blocked", payload={"step_id": step_id, "reason": reason or ""})
        return self._serialize_agent_state(updated)

    def replan_session(self, session_id: str) -> dict[str, Any]:
        namespace = self._session_namespace(session_id)
        state = self._load_agent_state(namespace)
        if state is None:
            raise KeyError(f"No planner state found for session {session_id}")
        updated = self._planning_agent().apply_execution_feedback(state, observations=["manual replan requested"])
        self._validate_plan(updated)
        self._persist_agent_state(namespace, updated, status="planning", objective=updated.objective)
        self.store.append_session_event(session_id, name="plan_replanned", payload={"todo_count": len(updated.todos)})
        return self._serialize_agent_state(updated)

    def export_plan(
        self,
        session_id: str,
        *,
        provider: str,
        profile_name: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any] | str:
        state = self._load_agent_state(self._session_namespace(session_id))
        if state is None:
            raise KeyError(f"No planner state found for session {session_id}")
        if provider == "chatgpt":
            return ChatGPTRenderer.render_progress_snapshot(state.plan, state.todos)
        if provider == "claude-code":
            return {
                "settings": ClaudeCodeRenderer.render_settings({"NANOCLI_SESSION_ID": session_id}),
                "claude_md": ClaudeCodeRenderer.render_claude_md(state.plan),
                "subagent": ClaudeCodeRenderer.render_subagent("planner", "Planning specialist", self.plan_skill.build_tools()),
            }
        if provider in {"openai", "anthropic", "deepseek", "glm", "kimi", "minimax"}:
            export_profile = self._resolve_plan_export_profile(session_id, provider, profile_name=profile_name, model=model)
            return self._planning_agent(provider=provider, model=export_profile.model).build_provider_request(state)
        raise KeyError(f"Unknown plan export provider: {provider}")

    def build_mcp_server(self) -> AsyncRuntimeMcpServer:
        catalog = build_builtin_tool_catalog(
            workspace_root=self.cwd,
            run_id="mcp-serve",
            session_id=None,
            allow_web=False,
            mounted_mcp_servers=[],
            mcp_manager=self.mcp,
            extra_tools=self.skills.build_runtime_tools(self.skills.load_selected(self.config.skills.enabled)),
            tool_options=self.config.tools,
        )
        return AsyncRuntimeMcpServer(
            workspace_root=self.cwd,
            tool_executor=catalog.registry,
            tool_notes=catalog.notes,
            resource_provider=self._mcp_resources_payload,
            prompt_provider=self._mcp_prompts_payload,
        )

    def _resolve_planner_skill(self):
        registry = {
            "repository_refactor": RepositoryRefactorSkill,
        }
        selected = self.config.planning.skill.strip().lower()
        if selected not in registry:
            raise KeyError(f"Unknown planner skill: {self.config.planning.skill}")
        return registry[selected]()

    def _resolve_mcp_runtime_plan(self, profile: ModelProfile) -> McpRuntimePlan:
        native_servers: list[McpServerConfig] = []
        mounted_servers: list[MountedMcpServer] = []
        provider = profile.provider
        for server in self.config.mcp_servers.values():
            mode = self._resolve_mcp_mode(server, provider)
            if mode == "native":
                native_servers.append(server)
            else:
                mounted_servers.append(MountedMcpServer(name=server.name, config=server, mode=mode))
        return McpRuntimePlan(native_servers=native_servers, mounted_servers=mounted_servers)

    def _resolve_mcp_mode(self, server: McpServerConfig, provider: str) -> str:
        return resolve_mcp_integration_mode(server, provider)

    @staticmethod
    def _provider_supports_native_mcp(provider: str, server: McpServerConfig) -> bool:
        return provider_supports_native_mcp(provider, server)

    def _default_mcp_mode(self, server: McpServerConfig, provider: str) -> str:
        if self._provider_supports_native_mcp(provider, server):
            return "native"
        return "flatten"

    def _mcp_resources_payload(self) -> dict[str, dict[str, Any]]:
        project_snapshot = self.read_project_memory_snapshot()
        latest_runs = self.list_runs(limit=5)
        latest_run = latest_runs[0] if latest_runs else None
        plan_snapshot = self._latest_plan_snapshot()
        latest_traces = self._latest_trace_payload(latest_run.run_id if latest_run else None)
        resources = {
            "nanocli://workspace/root": {
                "uri": "nanocli://workspace/root",
                "name": "workspace_root",
                "mimeType": "text/plain",
                "text": str(self.cwd),
            },
            "nanocli://memory/project": {
                "uri": "nanocli://memory/project",
                "name": "project_memory",
                "mimeType": "application/json",
                "text": json.dumps(project_snapshot, ensure_ascii=False, indent=2, default=str),
            },
            "nanocli://runs/latest": {
                "uri": "nanocli://runs/latest",
                "name": "latest_run",
                "mimeType": "application/json",
                "text": json.dumps(
                    {
                        "run_id": latest_run.run_id if latest_run else None,
                        "objective": latest_run.objective if latest_run else "",
                        "status": latest_run.status.value if latest_run else "empty",
                        "phase": latest_run.phase if latest_run else "idle",
                        "summary": latest_run.summary if latest_run else "",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
            "nanocli://planner/current": {
                "uri": "nanocli://planner/current",
                "name": "planner_state",
                "mimeType": "application/json",
                "text": json.dumps(plan_snapshot, ensure_ascii=False, indent=2),
            },
            "nanocli://traces/latest": {
                "uri": "nanocli://traces/latest",
                "name": "latest_traces",
                "mimeType": "application/json",
                "text": json.dumps(latest_traces, ensure_ascii=False, indent=2),
            },
        }
        return resources

    def _latest_plan_snapshot(self) -> dict[str, Any]:
        for session in self.list_sessions(limit=20):
            try:
                state = self.get_plan_state(session.session_id)
            except Exception:
                continue
            return {
                "session_id": session.session_id,
                "title": session.title,
                "profile": session.profile,
                "state": state,
            }
        return {
            "session_id": None,
            "title": "",
            "profile": "",
            "state": None,
        }

    def _latest_trace_payload(self, run_id: str | None) -> dict[str, Any]:
        if not run_id:
            return {"run_id": None, "trace_count": 0, "traces": []}
        traces = self.get_traces(run_id)
        return {
            "run_id": run_id,
            "trace_count": len(traces),
            "traces": [
                {
                    "trace_id": trace.trace_id,
                    "timestamp": trace.timestamp.isoformat(),
                    "kind": trace.kind.value,
                    "message": trace.message,
                    "artifact_path": trace.artifact_path,
                }
                for trace in traces
            ],
        }

    def _mcp_prompts_payload(self) -> dict[str, dict[str, Any]]:
        return {
            "planner": {
                "name": "planner",
                "description": "Summarize the active plan, todo frontier, and blocked execution state.",
                "messages": [
                    {
                        "role": "system",
                        "content": {
                            "type": "text",
                            "text": "Summarize the active plan, todo frontier, blockers, and open artifacts for this workspace.",
                        },
                    }
                ],
            },
            "memory-review": {
                "name": "memory-review",
                "description": "Review project memory sources, candidates, and promoted durable blocks.",
                "messages": [
                    {
                        "role": "system",
                        "content": {
                            "type": "text",
                            "text": "Inspect project sources, derived resources, and memory candidates before promoting durable memory.",
                        },
                    }
                ],
            },
        }

    def _planning_agent(self, provider: str | None = None, model: str | None = None) -> DualLayerPlanTodoAgent:
        adapter: BaseProviderAdapter
        if provider == "openai":
            adapter = PlanOpenAIResponsesAdapter(model=model or "gpt-5.4")
        elif provider == "anthropic":
            adapter = PlanAnthropicMessagesAdapter(model=model or "claude-sonnet-4.6")
        elif provider in {"deepseek", "glm", "kimi"}:
            adapter = OpenAIChatLikeAdapter(model=model or provider)
        elif provider == "minimax":
            adapter = PlanAnthropicMessagesAdapter(model=model or "MiniMax-M2.5")
        else:
            adapter = _NoopPlanProvider()
        return DualLayerPlanTodoAgent(provider=adapter, skill=self.plan_skill)

    def _bootstrap_state(self, objective: str) -> AgentState:
        return self._planning_agent().bootstrap(objective)

    def _validate_plan(self, state: AgentState) -> None:
        issues = self.critic.review(state.plan, self.plan_skill.build_tools())
        if issues:
            raise ValueError("Invalid planner state:\n- " + "\n- ".join(issues))

    def _load_agent_state(self, namespace: str) -> AgentState | None:
        execution = self.memory_store.get_execution_state(namespace)
        raw = execution.get("agent_state")
        if not raw:
            return None
        return self._deserialize_agent_state(json.loads(raw))

    def _persist_agent_state(
        self,
        namespace: str,
        state: AgentState,
        *,
        status: str,
        objective: str,
        blocked_reason: str | None = None,
    ) -> None:
        current_step = next((todo.content for todo in state.todos if todo.status == TodoStatus.IN_PROGRESS), state.todos[0].content if state.todos else "")
        payload = {
            "objective": objective,
            "status": status,
            "current_step": current_step,
            "completed_steps": json.dumps(state.completed_steps, ensure_ascii=False),
            "blocked_steps": json.dumps(state.blocked_steps, ensure_ascii=False),
            "active_todos": json.dumps([todo.to_dict() for todo in state.todos], ensure_ascii=False),
            "open_artifacts": json.dumps([], ensure_ascii=False),
            "agent_state": json.dumps(self._serialize_agent_state(state), ensure_ascii=False),
        }
        if blocked_reason:
            payload["blocked_reason"] = blocked_reason
        self.memory_store.replace_execution_state(namespace, payload)

    @staticmethod
    def _serialize_agent_state(state: AgentState) -> dict[str, Any]:
        return {
            "objective": state.objective,
            "plan": state.plan.to_dict(),
            "todos": [todo.to_dict() for todo in state.todos],
            "observations": list(state.observations),
            "completed_steps": list(state.completed_steps),
            "blocked_steps": list(state.blocked_steps),
        }

    @staticmethod
    def _deserialize_agent_state(payload: dict[str, Any]) -> AgentState:
        return AgentState(
            objective=str(payload["objective"]),
            plan=AgentRuntime._deserialize_plan(payload["plan"]),
            todos=[AgentRuntime._deserialize_todo(item) for item in payload.get("todos", [])],
            observations=list(payload.get("observations", [])),
            completed_steps=list(payload.get("completed_steps", [])),
            blocked_steps=list(payload.get("blocked_steps", [])),
        )

    @staticmethod
    def _deserialize_plan(payload: dict[str, Any]) -> Plan:
        return Plan(
            goal=str(payload["goal"]),
            assumptions=list(payload.get("assumptions", [])),
            constraints=list(payload.get("constraints", [])),
            deliverables=list(payload.get("deliverables", [])),
            steps=[
                PlanStep(
                    step_id=str(step["step_id"]),
                    title=str(step["title"]),
                    description=str(step["description"]),
                    kind=StepKind(step.get("kind", StepKind.ANALYZE.value)),
                    depends_on=list(step.get("depends_on", [])),
                    success_criteria=list(step.get("success_criteria", [])),
                    suggested_tools=list(step.get("suggested_tools", [])),
                    risk_notes=list(step.get("risk_notes", [])),
                    estimated_cost=str(step.get("estimated_cost", "medium")),
                )
                for step in payload.get("steps", [])
            ],
        )

    @staticmethod
    def _deserialize_todo(payload: dict[str, Any]) -> TodoItem:
        return TodoItem(
            todo_id=str(payload["todo_id"]),
            content=str(payload["content"]),
            active_form=str(payload.get("active_form", payload["content"])),
            linked_step_id=payload.get("linked_step_id"),
            status=TodoStatus(payload.get("status", TodoStatus.PENDING.value)),
            owner=str(payload.get("owner", "agent")),
            notes=str(payload.get("notes", "")),
        )

    def _runtime_control_messages(
        self,
        loaded_skills: list[LoadedSkill],
        subagent_summary: SubagentRunSummary | None,
    ) -> list[Message]:
        messages: list[Message] = []
        for skill in loaded_skills:
            lines = [f"[SKILL:{skill.name}] {skill.description}", skill.instructions.strip()]
            if skill.references:
                lines.append("References: " + ", ".join(sorted(skill.references)))
            if skill.instruction_only:
                lines.append("Runtime mode: instruction-only; no executable tools are mounted.")
            messages.append(Message(role=MessageRole.DEVELOPER, content="\n".join(lines).strip(), metadata={"skill": skill.name}))
        if subagent_summary is not None:
            messages.append(
                Message(
                    role=MessageRole.DEVELOPER,
                    content="[SUBAGENT_CONTEXT]\n" + subagent_summary.merged,
                    metadata={"selected_agents": list(subagent_summary.selected_agents)},
                )
            )
        return messages

    def _record_tool_observation(
        self,
        *,
        session_id: str | None,
        session_namespace: str,
        run_id: str,
        tool_call: ToolCall,
        execution: ToolExecution,
        observation: Message,
    ) -> None:
        self.memory.observe_session_message(session_namespace, observation, source="tool")
        if session_id:
            self.store.append_session_message(
                session_id,
                role="tool",
                content=observation.content,
                run_id=run_id,
                metadata={"tool_name": tool_call.name, "tool_call_id": tool_call.call_id},
            )
            self.store.append_session_event(
                session_id,
                name="tool_observation",
                payload={
                    "tool_name": tool_call.name,
                    "tool_call_id": tool_call.call_id,
                    "is_error": execution.is_error,
                },
                run_id=run_id,
            )

    def _persist_subagent_payload(self, run_id: str, *, session_id: str | None, payload: dict[str, Any]) -> None:
        for result in payload.get("results", []):
            agent_name = str(result["agent_name"])
            namespace = self._subagent_namespace(run_id, agent_name)
            artifact = self.store.save_artifact(run_id, f"subagent_{agent_name}", result)
            subagent_run_id = self.store.create_subagent_run(
                run_id=run_id,
                session_id=session_id,
                agent_name=agent_name,
                namespace=namespace,
                subgoal=agent_name,
                status="completed" if result.get("success", False) else "failed",
                artifact_path=artifact,
            )
            self.store.append_subagent_result(
                subagent_run_id,
                agent_name=agent_name,
                success=bool(result.get("success", False)),
                summary=str(result.get("summary", "")),
                structured_output=dict(result.get("structured_output", {})),
                evidence=list(result.get("evidence", [])),
                artifact_path=artifact,
            )
            self.memory.observe_session_message(namespace, Message(role=MessageRole.ASSISTANT, content=str(result.get("summary", ""))), source="subagent")
            for provider_artifact in payload.get("provider_artifacts", []):
                if provider_artifact.get("agent_name") != agent_name:
                    continue
                provider_path = self.store.save_artifact(
                    run_id,
                    f"subagent_provider_{agent_name}_{provider_artifact['provider']}",
                    provider_artifact,
                )
                self.store.append_subagent_provider_artifact(
                    subagent_run_id,
                    provider=str(provider_artifact["provider"]),
                    definition=provider_artifact["definition"],
                    invocation=provider_artifact["invocation_example"],
                    notes=list(provider_artifact.get("notes", [])),
                    artifact_path=provider_path,
                )
            working_memory_path = self.store.save_artifact(
                run_id,
                f"subagent_memory_{agent_name}",
                payload.get("working_memory", {}),
            )
            self.store.update_subagent_run(subagent_run_id, merged_summary=str(payload.get("merged", "")), artifact_path=working_memory_path)

    def _provider_extra(self, profile: ModelProfile, *, native_mcp_servers: list[McpServerConfig] | None = None) -> dict[str, Any]:
        extra = dict(profile.extra)
        extra.setdefault("max_tokens", profile.max_tokens)
        if native_mcp_servers:
            if profile.provider == "openai_responses":
                extra["native_mcp_tools"] = [self._openai_native_mcp_descriptor(server) for server in native_mcp_servers]
            elif profile.provider == "anthropic":
                extra["anthropic_mcp_servers"] = [self._anthropic_native_mcp_descriptor(server) for server in native_mcp_servers]
        return extra

    def _openai_native_mcp_descriptor(self, server: McpServerConfig) -> dict[str, Any]:
        descriptor: dict[str, Any] = {
            "type": "mcp",
            "server_label": server.native_label or server.name,
            "server_url": str(server.url),
            "require_approval": "never",
        }
        auth = self._native_mcp_authorization(server)
        if auth:
            descriptor["authorization"] = auth
        return descriptor

    def _anthropic_native_mcp_descriptor(self, server: McpServerConfig) -> dict[str, Any]:
        descriptor: dict[str, Any] = {
            "type": "url",
            "url": str(server.url),
            "name": server.native_label or server.name,
        }
        auth = self._native_mcp_authorization(server)
        if auth:
            descriptor["authorization_token"] = auth
        return descriptor

    def _native_mcp_authorization(self, server: McpServerConfig) -> str | None:
        headers = self.mcp.auth.headers_for(server)
        authorization = headers.get("Authorization")
        if authorization and authorization.lower().startswith("bearer "):
            return authorization.split(" ", 1)[1].strip()
        api_key = headers.get("X-API-Key")
        if api_key:
            return api_key
        return None

    def _invoke_provider(self, request: ProviderRequest, profile: ModelProfile, api_key: str) -> Any:
        if profile.provider in {"openai_responses", "openai_chat"}:
            runtime = OpenAIRuntime()
            return runtime.invoke(request, api_key=api_key, base_url=profile.base_url)
        if profile.provider == "anthropic":
            runtime = AnthropicRuntime()
            return runtime.invoke(request, api_key=api_key, base_url=profile.base_url)
        runtime = OpenAICompatibleRuntime()
        return runtime.invoke(request, api_key=api_key, base_url=profile.base_url)

    @staticmethod
    def _provider_request_dict(request: ProviderRequest) -> dict[str, Any]:
        return {
            "provider": request.provider.value,
            "endpoint_style": request.endpoint_style,
            "path": request.path,
            "payload": request.payload,
            "headers": request.headers,
            "diagnostics": request.diagnostics,
        }

    def _record_session_completion(
        self,
        session_id: str,
        *,
        run_id: str,
        profile: str,
        content: str,
        status: str,
    ) -> None:
        self.store.append_session_message(session_id, role="assistant", content=content, run_id=run_id)
        self.store.append_session_event(session_id, name="turn_completed", payload={"summary": content}, run_id=run_id)
        session = self.store.get_session(session_id)
        title = session.title
        if session.title == "Untitled session" and self.config.chat.auto_title_from_first_message:
            messages = self.store.list_session_messages(session_id, limit=1)
            if messages:
                title = self._title_from_prompt(messages[0].content)
        self.store.update_session(session_id, title=title, profile=profile, last_run_id=run_id, status=status)

    def _emit_disclosure(
        self,
        run_id: str,
        state: AgentState,
        kind: EventKind,
        objective: str,
        *,
        session_id: str | None = None,
        error: str | None = None,
        action_target: str | None = None,
    ) -> list[str]:
        snapshot = TaskStateSnapshot(
            task_id=run_id,
            goal=objective,
            current_step=next((todo.content for todo in state.todos if todo.status.value == "in_progress"), state.todos[0].content if state.todos else None),
            progress_current=len(state.completed_steps),
            progress_total=len(state.plan.steps),
            confidence=0.72 if error is None else 0.32,
            uncertainty_reasons=(error,) if error else (),
        )
        current_action = None
        if kind in {EventKind.ACTION_STARTED, EventKind.ACTION_COMPLETED}:
            current_action = ActionRecord(
                kind=ActionKind.EXECUTE,
                description="Call selected model provider",
                target=action_target,
                external_effect=True,
            )
        context = DisclosureContext(
            state=snapshot,
            phase=self._phase_for_event(kind),
            risk=TaskRisk.MEDIUM if error is None else TaskRisk.HIGH,
            preferences=DisclosurePreferences(),
            current_action=current_action,
            plan_outline=[step.title for step in state.plan.steps],
            blocked_reason=error,
        )
        message = self.disclosure.handle_event(AgentEvent(kind=kind, message=objective, payload={"run_id": run_id}), context)
        if message is None:
            return []
        artifact = self.store.save_artifact(
            run_id,
            f"disclosure_{kind.value}_{len(self.store.list_traces(run_id))}",
            {
                "title": message.title,
                "summary": message.summary,
                "body": message.body,
                "metadata": dict(message.metadata),
            },
        )
        self.store.append_trace(
            run_id,
            kind=TraceKind.DISCLOSURE,
            message=message.title,
            payload={"summary": message.summary, "require_approval": message.require_approval},
            artifact_path=artifact,
        )
        self.store.append_disclosure(
            run_id,
            session_id=session_id,
            title=message.title,
            summary=message.summary,
            require_approval=message.require_approval,
            artifact_path=artifact,
        )
        return [message.body]

    @staticmethod
    def _phase_for_event(kind: EventKind) -> AgentPhase:
        if kind in {EventKind.TASK_STARTED, EventKind.PLAN_CREATED, EventKind.PLAN_UPDATED}:
            return AgentPhase.PLANNING
        if kind in {EventKind.ACTION_STARTED, EventKind.ACTION_COMPLETED}:
            return AgentPhase.EXECUTION
        if kind == EventKind.ERROR:
            return AgentPhase.RECOVERY
        return AgentPhase.COMPLETE

    def _persist_project_memory(self, snapshot: dict[str, Any]) -> Path:
        path = self.paths.project_dir / "project_memory.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _resolve_plan_export_profile(self, session_id: str, provider: str, *, profile_name: str | None, model: str | None) -> ModelProfile:
        if model:
            if profile_name:
                profile = self.resolve_profile(profile_name)
                return ModelProfile(
                    name=profile.name,
                    provider=profile.provider,
                    model=model,
                    api_key_env=profile.api_key_env,
                    base_url=profile.base_url,
                    max_tokens=profile.max_tokens,
                    tool_mode=profile.tool_mode,
                    cache_mode=profile.cache_mode,
                    extra=dict(profile.extra),
                )
            provider_name = self._export_provider_name(provider)
            return ModelProfile(name=f"{provider}-export", provider=provider_name, model=model, api_key_env="")
        if profile_name:
            profile = self.resolve_profile(profile_name)
            if profile.provider != self._export_provider_name(provider):
                raise ValueError(f"Profile {profile.name} does not match export provider {provider}")
            return profile
        session_profile = self.get_session(session_id).profile
        if session_profile:
            profile = self.resolve_profile(session_profile)
            if profile.provider == self._export_provider_name(provider):
                return profile
        for profile in self.config.profiles.values():
            if profile.provider == self._export_provider_name(provider):
                return profile
        raise KeyError(f"No configured profile matches plan export provider {provider}")

    @staticmethod
    def _export_provider_name(provider: str) -> str:
        return {
            "openai": "openai_responses",
            "anthropic": "anthropic",
            "deepseek": "deepseek",
            "glm": "glm",
            "kimi": "kimi",
            "minimax": "minimax",
        }[provider]

    def _export_claude_memory(self, run_id: str) -> dict[str, str]:
        exporter = ClaudeCodeMemoryExporter()
        target = self.paths.artifacts_dir / run_id / "claude_export"
        return exporter.export(
            target,
            self.memory_store.list_control_blocks(self._project_namespace()),
            self.memory_store.list_blocks(self._project_namespace(), active_only=False),
        )

    @staticmethod
    def _coerce_json(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        if hasattr(value, "to_dict"):
            dumped = value.to_dict()
            if isinstance(dumped, dict):
                return dumped
        if isinstance(value, dict):
            return value
        if hasattr(value, "__dict__"):
            return json.loads(json.dumps(value.__dict__, ensure_ascii=False, default=str))
        return {"value": str(value)}

    @staticmethod
    def _extract_response_text(response: dict[str, Any]) -> str:
        if "output_text" in response:
            return str(response.get("output_text") or "")
        if "output" in response:
            chunks: list[str] = []
            for item in response.get("output", []):
                if item.get("type") == "message":
                    for block in item.get("content", []):
                        if block.get("type") in {"output_text", "text"}:
                            chunks.append(block.get("text", ""))
            return "".join(chunks).strip()
        if "choices" in response:
            choice = response.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content")
            return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        if "content" in response:
            return "".join(block.get("text", "") for block in response.get("content", []) if isinstance(block, dict))
        return ""

    def _project_namespace(self) -> str:
        digest = sha1(str(self.cwd).encode("utf-8")).hexdigest()[:16]
        return f"project:{digest}"

    @staticmethod
    def _session_namespace(session_id: str) -> str:
        return f"session:{session_id}"

    @staticmethod
    def _run_namespace(run_id: str) -> str:
        return f"run:{run_id}"

    @staticmethod
    def _subagent_namespace(run_id: str, agent_name: str) -> str:
        return f"subagent:{run_id}:{agent_name}"

    @staticmethod
    def _title_from_prompt(prompt: str) -> str:
        clean = " ".join(prompt.strip().split())
        return clean[:60] or "Untitled session"
