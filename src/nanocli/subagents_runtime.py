from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from subagent_framework.abstractions import AbstractSubAgent
from subagent_framework.agents import ResearchSubAgent
from subagent_framework.memory import HierarchicalWorkingMemory
from subagent_framework.models import ExecutionTrace, SubAgentDefinition, TaskEnvelope, TaskResult, WorkingMemorySnapshot
from subagent_framework.orchestrator import SubAgentOrchestrator, SubAgentRegistry
from subagent_framework.providers import ClaudeCodeAdapter, DeepSeekAdapter, GLMAdapter, KimiAdapter, MiniMaxAdapter, OpenAIChatGPTAdapter
from subagent_framework.router import KeywordCapabilityRouter

from .models import SubagentRunSummary


class ReviewSubAgent(AbstractSubAgent):
    def __init__(self) -> None:
        self.definition = SubAgentDefinition(
            name="review-critic",
            description="Review specialist for bug risks, regressions, missing tests, and operational hazards.",
            system_prompt="Review the proposed work like a staff engineer focusing on regressions and test coverage.",
            instructions="Surface concrete risks, likely failure modes, and the minimum verification needed.",
            tags=["review", "risk", "bug", "regression", "test", "qa"],
            capabilities=["code-review", "risk-assessment", "test-gap-analysis"],
        )

    def can_handle(self, task: TaskEnvelope) -> bool:
        lowered = task.user_query.lower()
        return any(token in lowered for token in ["review", "risk", "bug", "test", "regression", "qa", "验证", "检查"])

    async def arun(self, task: TaskEnvelope, memory: WorkingMemorySnapshot) -> TaskResult:
        issues = self._extract_focus(task.user_query)
        traces = [
            ExecutionTrace(
                phase="review",
                agent_name=self.definition.name,
                message="identified high-risk review dimensions",
                payload={"focus": issues},
            )
        ]
        return TaskResult(
            success=True,
            agent_name=self.definition.name,
            summary="Mapped the task to likely regression and testing hotspots.",
            evidence=[
                f"focus={', '.join(issues[:6]) or 'general correctness'}",
                f"prior_memory={len(memory.active_entries)} focused entries",
                "recommended verification=unit + integration + smoke",
            ],
            structured_output={"focus": issues},
            traces=traces,
        )

    @staticmethod
    def _extract_focus(text: str) -> list[str]:
        return re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", text.lower())


class ImplementationSubAgent(AbstractSubAgent):
    def __init__(self) -> None:
        self.definition = SubAgentDefinition(
            name="implementation-builder",
            description="Implementation specialist for coding, refactoring, decomposition, and integration sequencing.",
            system_prompt="Turn objectives into build steps, interfaces, and implementation sequencing.",
            instructions="Prefer simple integration points, low-risk edits, and explicit ownership boundaries.",
            tags=["implement", "build", "code", "refactor", "integrate"],
            capabilities=["implementation-plan", "refactor-plan", "interface-design"],
        )

    def can_handle(self, task: TaskEnvelope) -> bool:
        lowered = task.user_query.lower()
        return any(token in lowered for token in ["implement", "build", "code", "refactor", "integrate", "fix", "实现", "重构"])

    async def arun(self, task: TaskEnvelope, memory: WorkingMemorySnapshot) -> TaskResult:
        steps = self._derive_steps(task.user_query)
        traces = [
            ExecutionTrace(
                phase="plan",
                agent_name=self.definition.name,
                message="derived implementation slices",
                payload={"steps": steps},
            )
        ]
        return TaskResult(
            success=True,
            agent_name=self.definition.name,
            summary="Derived an implementation-first integration sequence with minimal coupling.",
            evidence=[f"steps={len(steps)}", *[f"step={step}" for step in steps[:4]]],
            structured_output={"steps": steps, "memory_entries": len(memory.active_entries)},
            traces=traces,
        )

    @staticmethod
    def _derive_steps(text: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", text.lower())
        unique = list(dict.fromkeys(tokens))
        if not unique:
            return ["scope task", "edit runtime", "verify behavior"]
        return [f"handle {token}" for token in unique[:5]]


@dataclass(slots=True)
class SubagentManager:
    max_parallel_agents: int = 3
    timeout_seconds: int = 60
    registry: SubAgentRegistry | None = None
    orchestrator: SubAgentOrchestrator | None = None
    memory: HierarchicalWorkingMemory | None = None

    def __post_init__(self) -> None:
        registry = SubAgentRegistry()
        for agent in self._default_agents():
            registry.register(agent)
        self.registry = registry
        memory = HierarchicalWorkingMemory()
        self.memory = memory
        self.orchestrator = SubAgentOrchestrator(
            registry=registry,
            router=KeywordCapabilityRouter(max_parallel_agents=self.max_parallel_agents),
            memory=memory,
        )

    @staticmethod
    def _default_agents() -> list[AbstractSubAgent]:
        return [
            ResearchSubAgent(),
            ReviewSubAgent(),
            ImplementationSubAgent(),
        ]

    def available_agents(self) -> list[dict[str, Any]]:
        agents: list[dict[str, Any]] = []
        if self.registry is None:
            return agents
        for agent in self.registry.values():
            agents.append(
                {
                    "name": agent.definition.name,
                    "description": agent.definition.description,
                    "tags": list(agent.definition.tags),
                    "capabilities": list(agent.definition.capabilities),
                }
            )
        return agents

    def should_delegate(self, query: str, keywords: list[str]) -> bool:
        lowered = query.lower()
        return any(keyword.lower() in lowered for keyword in keywords)

    def run(
        self,
        *,
        task_id: str,
        query: str,
        subgoal: str | None = None,
        shared_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        envelope = TaskEnvelope(
            task_id=task_id,
            user_query=query,
            subgoal=subgoal,
            shared_context=shared_context or {},
        )
        if self.orchestrator is None:
            raise RuntimeError("subagent orchestrator is not initialized")
        result = asyncio.run(asyncio.wait_for(self.orchestrator.arun(envelope), timeout=self.timeout_seconds))
        selected_agents = list(result["decision"].selected_agents)
        return {
            "decision": {
                "selected_agents": selected_agents,
                "parallel": result["decision"].parallel,
                "reason": result["decision"].reason,
                "scores": dict(result["decision"].scores),
            },
            "results": [
                {
                    "agent_name": item.agent_name,
                    "success": item.success,
                    "summary": item.summary,
                    "structured_output": item.structured_output,
                    "evidence": list(item.evidence),
                    "traces": [self._trace_to_dict(trace) for trace in item.traces],
                }
                for item in result["results"]
            ],
            "merged": result["merged"],
            "traces": [self._trace_to_dict(trace) for trace in result["traces"]],
            "working_memory": self._snapshot_to_dict(self.snapshot_memory(envelope.subgoal or None)),
            "provider_artifacts": self.export_artifacts(selected_agents=selected_agents, sample_task=query),
        }

    def summarize(self, run_id: str, payload: dict[str, Any]) -> SubagentRunSummary:
        return SubagentRunSummary(
            run_id=run_id,
            selected_agents=list(payload["decision"]["selected_agents"]),
            merged=str(payload["merged"]),
            traces=list(payload["traces"]),
        )

    def export_artifacts(
        self,
        *,
        selected_agents: list[str] | None = None,
        sample_task: str,
        providers: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self.registry is None:
            return []
        adapters = self._provider_adapters()
        selected = set(selected_agents or [agent.definition.name for agent in self.registry.values()])
        provider_filter = set(providers or adapters.keys())
        artifacts: list[dict[str, Any]] = []
        for agent in self.registry.values():
            if agent.definition.name not in selected:
                continue
            for provider_name, adapter in adapters.items():
                if provider_name not in provider_filter:
                    continue
                artifact = adapter.build_artifact(agent.definition, sample_task)
                artifacts.append(
                    {
                        "agent_name": agent.definition.name,
                        "provider": artifact.provider,
                        "definition": artifact.definition,
                        "invocation_example": artifact.invocation_example,
                        "notes": list(artifact.notes),
                    }
                )
        return artifacts

    def snapshot_memory(self, active_subgoal: str | None = None) -> WorkingMemorySnapshot:
        if self.memory is None:
            return WorkingMemorySnapshot(active_subgoal=None, active_entries=[], archived_summaries={})
        return self.memory.snapshot(active_subgoal)

    @staticmethod
    def _trace_to_dict(trace: ExecutionTrace) -> dict[str, Any]:
        return {
            "phase": trace.phase,
            "message": trace.message,
            "agent_name": trace.agent_name,
            "payload": dict(trace.payload),
            "created_at": trace.created_at,
        }

    @staticmethod
    def _snapshot_to_dict(snapshot: WorkingMemorySnapshot) -> dict[str, Any]:
        return {
            "active_subgoal": snapshot.active_subgoal,
            "active_entries": [
                {
                    "subgoal": entry.subgoal,
                    "observation": entry.observation,
                    "compact_summary": entry.compact_summary,
                    "metadata": dict(entry.metadata),
                    "created_at": entry.created_at,
                }
                for entry in snapshot.active_entries
            ],
            "archived_summaries": dict(snapshot.archived_summaries),
        }

    @staticmethod
    def _provider_adapters() -> dict[str, Any]:
        return {
            "openai_chatgpt": OpenAIChatGPTAdapter(),
            "claude_code": ClaudeCodeAdapter(),
            "deepseek": DeepSeekAdapter(),
            "glm": GLMAdapter(),
            "kimi": KimiAdapter(),
            "minimax": MiniMaxAdapter(),
        }
