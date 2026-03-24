from __future__ import annotations

from typing import Dict, List
import json

from plan_todo_agent.core.schemas import Plan, TodoItem


class ChatGPTRenderer:
    """Render product-facing structures inspired by ChatGPT Projects / Tasks.

    This is not an official API surface. It is an app-facing representation that helps
    teams keep parity between an internal agent and ChatGPT-style task organization.
    """

    @staticmethod
    def render_project_stub(name: str, objective: str, files: List[str] | None = None) -> Dict[str, object]:
        return {
            "project_name": name,
            "objective": objective,
            "files": files or [],
            "memory_mode": "project",
        }

    @staticmethod
    def render_task_stub(title: str, instructions: str, schedule: str) -> Dict[str, str]:
        return {
            "title": title,
            "instructions": instructions,
            "schedule": schedule,
        }

    @staticmethod
    def render_progress_snapshot(plan: Plan, todos: List[TodoItem]) -> str:
        payload = {
            "goal": plan.goal,
            "deliverables": plan.deliverables,
            "todos": [todo.to_dict() for todo in todos],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
