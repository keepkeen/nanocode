from __future__ import annotations

from typing import List, Set

from plan_todo_agent.core.interfaces import BaseTodoProjector
from plan_todo_agent.core.schemas import Plan, TodoItem, TodoStatus


class DependencyAwareTodoProjector(BaseTodoProjector):
    """Project the currently executable plan frontier into a small todo list."""

    def project(self, plan: Plan, completed_steps: List[str], blocked_steps: List[str]) -> List[TodoItem]:
        done: Set[str] = set(completed_steps)
        blocked: Set[str] = set(blocked_steps)
        todos: List[TodoItem] = []

        for step in plan.steps:
            if step.step_id in done:
                todos.append(
                    TodoItem(
                        todo_id=f"todo-{step.step_id}",
                        content=step.title,
                        active_form=f"Finalize: {step.title}",
                        linked_step_id=step.step_id,
                        status=TodoStatus.COMPLETED,
                    )
                )
                continue

            deps_satisfied = all(dep in done for dep in step.depends_on)
            if step.step_id in blocked:
                status = TodoStatus.BLOCKED
            elif deps_satisfied and not blocked:
                status = TodoStatus.IN_PROGRESS if not any(t.status == TodoStatus.IN_PROGRESS for t in todos) else TodoStatus.PENDING
            else:
                status = TodoStatus.PENDING

            todos.append(
                TodoItem(
                    todo_id=f"todo-{step.step_id}",
                    content=step.title,
                    active_form=f"Working on: {step.title}",
                    linked_step_id=step.step_id,
                    status=status,
                )
            )

        return todos
