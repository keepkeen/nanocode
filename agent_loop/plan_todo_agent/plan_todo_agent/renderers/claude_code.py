from __future__ import annotations

from typing import Dict, List
import json

from plan_todo_agent.core.schemas import Plan, ToolSpec


class ClaudeCodeRenderer:
    """Render Claude Code-specific assets.

    Claude Code is a client/runtime, so the useful outputs are settings, subagents,
    and guidance files rather than a single model payload.
    """

    @staticmethod
    def render_settings(provider_env: Dict[str, str], default_mode: str = "plan") -> str:
        payload = {
            "permissions": {
                "defaultMode": default_mode,
            },
            "env": provider_env,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def render_subagent(name: str, description: str, tools: List[ToolSpec]) -> str:
        tool_names = ", ".join(tool.name for tool in tools) or "Read"
        body = [
            "---",
            f"name: {name}",
            f"description: {description}",
            "---",
            "",
            "You are a specialized planning-and-execution subagent.",
            "Keep a stable plan, maintain a short todo frontier, and explain blockers early.",
            f"Allowed tools: {tool_names}",
        ]
        return "\n".join(body)

    @staticmethod
    def render_claude_md(plan: Plan) -> str:
        lines = [
            "# Project planning conventions",
            "",
            "## Operating rules",
            "- Start in plan mode for unfamiliar or multi-file changes.",
            "- Keep the global plan stable unless dependencies change.",
            "- Keep a short active todo list for the current frontier.",
            "- Mark blockers explicitly before editing unrelated files.",
            "",
            "## Current baseline plan",
            f"Goal: {plan.goal}",
            "",
        ]
        for step in plan.steps:
            lines.append(f"- {step.step_id}: {step.title}")
        return "\n".join(lines)
