from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence


JsonDict = Dict[str, Any]


@dataclass(slots=True)
class ToolSpec:
    """Provider-agnostic tool schema used by the sub-agent framework."""

    name: str
    description: str
    parameters: JsonDict


@dataclass(slots=True)
class SubAgentDefinition:
    """Canonical definition that can be serialized to multiple vendor formats."""

    name: str
    description: str
    system_prompt: str
    instructions: str
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    tools: List[ToolSpec] = field(default_factory=list)
    model_preferences: Dict[str, str] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    allow_parallel: bool = True
    metadata: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class TaskEnvelope:
    """Structured task input for orchestration."""

    task_id: str
    user_query: str
    subgoal: Optional[str] = None
    shared_context: JsonDict = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionTrace:
    phase: str
    message: str
    agent_name: Optional[str] = None
    payload: JsonDict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class TaskResult:
    success: bool
    agent_name: str
    summary: str
    structured_output: JsonDict = field(default_factory=dict)
    evidence: List[str] = field(default_factory=list)
    traces: List[ExecutionTrace] = field(default_factory=list)


@dataclass(slots=True)
class DelegationDecision:
    selected_agents: List[str]
    parallel: bool
    reason: str
    scores: Dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderArtifact:
    provider: str
    definition: Any
    invocation_example: Any
    notes: List[str] = field(default_factory=list)


@dataclass(slots=True)
class MemoryEntry:
    subgoal: str
    observation: str
    compact_summary: Optional[str] = None
    metadata: JsonDict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class WorkingMemorySnapshot:
    active_subgoal: Optional[str]
    active_entries: List[MemoryEntry]
    archived_summaries: Dict[str, str]



def merge_json(base: Mapping[str, Any], override: Mapping[str, Any]) -> JsonDict:
    """A tiny recursive dict merge used by provider serializers."""

    merged: JsonDict = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], MutableMapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = merge_json(merged[key], value)
        else:
            merged[key] = value
    return merged
