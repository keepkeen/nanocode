from __future__ import annotations

from typing import List, Set

from plan_todo_agent.core.interfaces import BasePlanCritic
from plan_todo_agent.core.schemas import Plan, ToolSpec


class HeuristicPlanCritic(BasePlanCritic):
    """A lightweight critic inspired by recent planning literature.

    It checks structure before the agent commits to execution.
    """

    def review(self, plan: Plan, tools: List[ToolSpec]) -> List[str]:
        issues: List[str] = []
        tool_names: Set[str] = {tool.name for tool in tools}
        step_ids: Set[str] = {step.step_id for step in plan.steps}

        if not plan.steps:
            issues.append("Plan has no steps.")

        if not plan.deliverables:
            issues.append("Plan has no explicit deliverables.")

        for step in plan.steps:
            if not step.success_criteria:
                issues.append(f"Step {step.step_id} is missing success criteria.")
            for dep in step.depends_on:
                if dep not in step_ids:
                    issues.append(f"Step {step.step_id} depends on unknown step {dep}.")
            for tool_name in step.suggested_tools:
                if tool_name not in tool_names:
                    issues.append(f"Step {step.step_id} references unknown tool {tool_name}.")

        return issues
