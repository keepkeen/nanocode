from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json

from plan_todo_agent.core.interfaces import BaseProviderAdapter, BaseSkill
from plan_todo_agent.core.prompts import build_system_prompt, build_user_prompt
from plan_todo_agent.core.schemas import AgentTurn, Plan, TodoItem
from plan_todo_agent.planning.critic import HeuristicPlanCritic
from plan_todo_agent.planning.projector import DependencyAwareTodoProjector


@dataclass(slots=True)
class AgentState:
    objective: str
    plan: Plan
    todos: List[TodoItem]
    observations: List[str] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    blocked_steps: List[str] = field(default_factory=list)

    def to_turn(self) -> AgentTurn:
        return AgentTurn(
            objective=self.objective,
            plan=self.plan,
            todos=self.todos,
            observations=list(self.observations),
            completed_steps=list(self.completed_steps),
            blocked_steps=list(self.blocked_steps),
        )


class DualLayerPlanTodoAgent:
    """A planning-first agent with stable global plan + mutable local todo frontier."""

    def __init__(self, provider: BaseProviderAdapter, skill: BaseSkill) -> None:
        self.provider = provider
        self.skill = skill
        self.critic = HeuristicPlanCritic()
        self.projector = DependencyAwareTodoProjector()

    def bootstrap(self, objective: str) -> AgentState:
        plan = self.skill.bootstrap_plan(objective)
        tools = self.skill.build_tools()
        issues = self.critic.review(plan, tools)
        if issues:
            raise ValueError("Invalid bootstrap plan:\n- " + "\n- ".join(issues))

        todos = self.projector.project(plan, completed_steps=[], blocked_steps=[])
        return AgentState(objective=objective, plan=plan, todos=todos)

    def build_provider_request(self, state: AgentState) -> Dict[str, Any]:
        turn = state.to_turn()
        tools = self.skill.build_tools()
        system_prompt = build_system_prompt(self.skill.context, tools)
        user_prompt = build_user_prompt(turn)
        return self.provider.build_request(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=tools,
            turn=turn,
        )

    def apply_execution_feedback(
        self,
        state: AgentState,
        *,
        completed_step_ids: Optional[List[str]] = None,
        blocked_step_ids: Optional[List[str]] = None,
        observations: Optional[List[str]] = None,
    ) -> AgentState:
        completed = set(state.completed_steps)
        blocked = set(state.blocked_steps)

        for step_id in completed_step_ids or []:
            completed.add(step_id)
            blocked.discard(step_id)

        for step_id in blocked_step_ids or []:
            if step_id not in completed:
                blocked.add(step_id)

        new_observations = list(state.observations)
        new_observations.extend(observations or [])

        new_todos = self.projector.project(
            state.plan,
            completed_steps=sorted(completed),
            blocked_steps=sorted(blocked),
        )

        return AgentState(
            objective=state.objective,
            plan=state.plan,
            todos=new_todos,
            observations=new_observations,
            completed_steps=sorted(completed),
            blocked_steps=sorted(blocked),
        )

    def summarize_state(self, state: AgentState) -> str:
        data = state.to_turn().to_dict()
        return json.dumps(data, ensure_ascii=False, indent=2)
