from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    CREATED = "created"
    PLANNED = "planned"
    COMPILED = "compiled"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TraceKind(str, Enum):
    EVENT = "event"
    PLAN = "plan"
    MEMORY = "memory"
    PROVIDER_REQUEST = "provider_request"
    PROVIDER_RESPONSE = "provider_response"
    DISCLOSURE = "disclosure"
    TOOL = "tool"
    NOTE = "note"


@dataclass(slots=True)
class ModelProfile:
    name: str
    provider: str
    model: str
    api_key_env: str
    base_url: str | None = None
    max_tokens: int = 4096
    tool_mode: str = "auto"
    cache_mode: str = "auto"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChatOptions:
    default_repl_profile: str | None = None
    session_history_limit: int = 200
    auto_title_from_first_message: bool = True
    refresh_interval_ms: int = 1500
    stream_text: bool = True


@dataclass(slots=True)
class MemoryOptions:
    recent_turns: int = 8
    compaction_event_threshold: int = 18
    promotion_min_stability: float = 0.72
    promotion_min_salience: float = 0.7
    candidate_min_evidence: int = 2
    durable_kinds: list[str] = field(
        default_factory=lambda: ["preference", "fact", "constraint", "decision", "style", "tool_manifest", "policy"]
    )
    candidate_kinds: list[str] = field(
        default_factory=lambda: ["preference", "fact", "constraint", "decision", "style"]
    )
    explicit_source_patterns: list[str] = field(
        default_factory=lambda: ["AGENTS.md", "CLAUDE.md", ".nanocli/project.md", ".nanocli/memory/**/*.md"]
    )
    import_continue_rules: bool = True
    import_openhands_microagents: bool = True
    derive_repo_map: bool = True
    derive_repo_overview: bool = True


@dataclass(slots=True)
class SkillsOptions:
    project_paths: list[str] = field(default_factory=lambda: [".nanocli/skills"])
    user_paths: list[str] = field(default_factory=list)
    enabled: list[str] = field(default_factory=list)
    runtime_entrypoint: str = "skill.py"
    auto_render_targets: list[str] = field(
        default_factory=lambda: [
            "chatgpt",
            "claude-code",
            "claude-subagent",
            "deepseek",
            "glm",
            "kimi",
            "minimax-openai",
            "minimax-anthropic",
        ]
    )


@dataclass(slots=True)
class ToolOptions:
    web_search_provider: str = "tavily"
    allow_private_network: bool = False
    allow_shell_compounds: bool = False
    require_url_provenance: bool = True


@dataclass(slots=True)
class PlanningOptions:
    skill: str = "repository_refactor"


@dataclass(slots=True)
class SubagentOptions:
    enabled: bool = True
    max_parallel_agents: int = 3
    timeout_seconds: int = 60
    auto_delegate_keywords: list[str] = field(default_factory=lambda: ["research", "review", "analyze", "benchmark", "architecture", "plan"])


@dataclass(slots=True)
class UIOptions:
    theme: str = "default"


@dataclass(slots=True)
class ExperimentalOptions:
    subagents: bool = False


@dataclass(slots=True)
class McpServerConfig:
    name: str
    transport: str
    url: str | None = None
    command: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    integration_mode: str = "auto"
    startup_timeout_seconds: int = 15
    native_label: str | None = None
    protocol_version: str = "2025-11-25"
    fallback_protocol_versions: list[str] = field(default_factory=lambda: ["2025-06-18"])
    legacy_sse_fallback: bool = True
    headers: dict[str, str] = field(default_factory=dict)
    auth_mode: str = "none"
    auth_token_env: str | None = None
    connect_timeout_seconds: int = 15
    request_timeout_seconds: int = 60
    keepalive_seconds: int = 30
    max_inflight_requests: int = 16
    capabilities: dict[str, Any] = field(default_factory=dict)
    sampling_policy: str = "ask"
    elicitation_policy: str = "ask"
    roots_policy: str = "workspace"
    resume_streams: bool = True


@dataclass(slots=True)
class LiveTestOptions:
    enabled: bool = False
    provider_envs: dict[str, str] = field(
        default_factory=lambda: {
            "openai_responses": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }
    )
    timeout_seconds: int = 60


@dataclass(slots=True)
class NanocliPaths:
    global_config: Path
    project_config: Path
    data_dir: Path
    project_dir: Path
    db_path: Path
    artifacts_dir: Path


@dataclass(slots=True)
class NanocliConfig:
    default_profile: str
    profiles: dict[str, ModelProfile]
    chat: ChatOptions = field(default_factory=ChatOptions)
    memory: MemoryOptions = field(default_factory=MemoryOptions)
    skills: SkillsOptions = field(default_factory=SkillsOptions)
    tools: ToolOptions = field(default_factory=ToolOptions)
    planning: PlanningOptions = field(default_factory=PlanningOptions)
    subagents: SubagentOptions = field(default_factory=SubagentOptions)
    ui: UIOptions = field(default_factory=UIOptions)
    experimental: ExperimentalOptions = field(default_factory=ExperimentalOptions)
    live_tests: LiveTestOptions = field(default_factory=LiveTestOptions)
    mcp_servers: dict[str, McpServerConfig] = field(default_factory=dict)
    system_policies: list[str] = field(default_factory=list)
    user_instructions: list[str] = field(default_factory=list)
    paths: NanocliPaths | None = None


@dataclass(slots=True)
class RunSummary:
    run_id: str
    created_at: datetime
    updated_at: datetime
    objective: str
    profile: str
    cwd: Path
    status: RunStatus
    phase: str
    summary: str = ""
    error: str | None = None


@dataclass(slots=True)
class TraceRecord:
    trace_id: int
    run_id: str
    timestamp: datetime
    kind: TraceKind
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    artifact_path: str | None = None


@dataclass(slots=True)
class SessionSummary:
    session_id: str
    created_at: datetime
    updated_at: datetime
    title: str
    profile: str
    cwd: Path
    status: str
    last_run_id: str | None = None


@dataclass(slots=True)
class SessionMessageRecord:
    message_id: int
    session_id: str
    created_at: datetime
    role: str
    content: str
    run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LoadedSkill:
    name: str
    title: str
    description: str
    root_dir: Path
    instructions: str
    references: dict[str, str] = field(default_factory=dict)
    scripts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    instruction_only: bool = False
    entrypoint: str | None = None


@dataclass(slots=True)
class SubagentRunSummary:
    run_id: str
    selected_agents: list[str]
    merged: str
    traces: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class RunResult:
    summary: RunSummary
    traces: list[TraceRecord]
    plan_json: str
    todo_items: list[dict[str, Any]]
    memory_export: dict[str, Any]
    provider_request: dict[str, Any] | None = None
    provider_response: dict[str, Any] | None = None
    disclosures: list[str] = field(default_factory=list)
    session_id: str | None = None
    subagent_summary: SubagentRunSummary | None = None
