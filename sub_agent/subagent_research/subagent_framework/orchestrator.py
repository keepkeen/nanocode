from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence

from .abstractions import AbstractMemory, AbstractRouter, AbstractSubAgent
from .memory import HierarchicalWorkingMemory
from .models import DelegationDecision, ExecutionTrace, TaskEnvelope, TaskResult
from .router import KeywordCapabilityRouter


@dataclass(slots=True)
class SubAgentRegistry:
    agents: Dict[str, AbstractSubAgent] = field(default_factory=dict)

    def register(self, agent: AbstractSubAgent) -> None:
        self.agents[agent.definition.name] = agent

    def values(self) -> Sequence[AbstractSubAgent]:
        return list(self.agents.values())


class SubAgentOrchestrator:
    """Main coordinator that routes work, executes sub-agents, and merges outputs."""

    def __init__(
        self,
        registry: SubAgentRegistry,
        router: AbstractRouter | None = None,
        memory: AbstractMemory | None = None,
    ) -> None:
        self.registry = registry
        self.router = router or KeywordCapabilityRouter()
        self.memory = memory or HierarchicalWorkingMemory()

    async def arun(self, task: TaskEnvelope) -> dict:
        decision = self.router.decide(task, self.registry.values())
        traces = [
            ExecutionTrace(
                phase="route",
                message=decision.reason,
                payload={"scores": decision.scores, "selected_agents": decision.selected_agents},
            )
        ]

        if not decision.selected_agents:
            return {
                "decision": decision,
                "results": [],
                "merged": "No suitable sub-agent was selected.",
                "traces": traces,
            }

        results = await self._execute(task, decision)
        for result in results:
            observation = result.summary
            subgoal = task.subgoal or result.agent_name
            self.memory.remember(result.agent_name, subgoal, observation)
            traces.extend(result.traces)

        merged = self._merge_results(task, results, decision)
        traces.append(
            ExecutionTrace(
                phase="merge",
                message="merged sub-agent outputs",
                payload={"result_count": len(results)},
            )
        )
        return {
            "decision": decision,
            "results": results,
            "merged": merged,
            "traces": traces,
        }

    async def _execute(self, task: TaskEnvelope, decision: DelegationDecision) -> List[TaskResult]:
        coroutines = []
        for agent_name in decision.selected_agents:
            agent = self.registry.agents[agent_name]
            snapshot = self.memory.snapshot(task.subgoal or agent_name)
            coroutines.append(agent.arun(task, snapshot))
        return list(await asyncio.gather(*coroutines))

    @staticmethod
    def _merge_results(
        task: TaskEnvelope,
        results: Sequence[TaskResult],
        decision: DelegationDecision,
    ) -> str:
        header = f"Task: {task.user_query}\nDelegation: {', '.join(decision.selected_agents)}"
        bodies = []
        for result in results:
            bullets = "\n".join(f"- {item}" for item in result.evidence)
            bodies.append(
                f"[{result.agent_name}] {result.summary}\n{bullets}".strip()
            )
        return header + "\n\n" + "\n\n".join(bodies)
