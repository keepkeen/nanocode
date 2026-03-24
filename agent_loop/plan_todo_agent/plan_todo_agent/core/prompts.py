from __future__ import annotations

from typing import List

from .schemas import AgentTurn, SkillContext, ToolSpec


PLAN_JSON_SCHEMA_TEXT = """
Return a JSON object with the following shape:
{
  "summary": "short natural language summary",
  "next_action": "what to do next",
  "todo_updates": [
    {
      "todo_id": "string",
      "status": "pending|in_progress|completed|blocked|canceled",
      "notes": "optional"
    }
  ],
  "tool_intent": [
    {
      "tool_name": "string",
      "why": "why this tool is needed now"
    }
  ]
}
""".strip()


def render_tool_catalog(tools: List[ToolSpec]) -> str:
    lines: List[str] = []
    for tool in tools:
        lines.append(f"- {tool.name}: {tool.description}")
    return "\n".join(lines)


def render_skill_context(skill: SkillContext) -> str:
    parts = [
        f"Skill: {skill.name}",
        f"Description: {skill.description}",
    ]
    if skill.success_definition:
        parts.append("Success definition:")
        parts.extend([f"- {item}" for item in skill.success_definition])
    if skill.planning_hints:
        parts.append("Planning hints:")
        parts.extend([f"- {item}" for item in skill.planning_hints])
    if skill.extra_instructions:
        parts.append("Extra instructions:")
        parts.extend([f"- {item}" for item in skill.extra_instructions])
    return "\n".join(parts)


def render_turn_state(turn: AgentTurn) -> str:
    lines = [
        f"Objective: {turn.objective}",
        "Plan:",
        turn.plan.to_pretty_json(),
        "Todos:",
    ]
    lines.extend([f"- [{todo.status.value}] {todo.todo_id}: {todo.content}" for todo in turn.todos])
    if turn.observations:
        lines.append("Observations:")
        lines.extend([f"- {obs}" for obs in turn.observations])
    return "\n".join(lines)


def build_system_prompt(skill: SkillContext, tools: List[ToolSpec]) -> str:
    return "\n\n".join(
        [
            "You are a planning-first agent that separates long-horizon planning from short-horizon execution.",
            render_skill_context(skill),
            "Available tools:\n" + render_tool_catalog(tools),
            "Always keep a stable global plan, update only the active todos, and call tools only when they unblock the next frontier.",
        ]
    )


def build_user_prompt(turn: AgentTurn) -> str:
    return "\n\n".join(
        [
            render_turn_state(turn),
            "Update the active execution frontier.",
            "Do not rewrite the full plan unless observations invalidate dependencies or success criteria.",
            PLAN_JSON_SCHEMA_TEXT,
        ]
    )
