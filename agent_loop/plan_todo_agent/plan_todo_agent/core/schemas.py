from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
import json


class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELED = "canceled"


class StepKind(str, Enum):
    ANALYZE = "analyze"
    SEARCH = "search"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    REVIEW = "review"
    DELIVER = "deliver"


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    strict: bool = True
    read_only: bool = False

    def to_openai_tool(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": self.strict,
        }

    def to_openai_chat_tool(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                "strict": self.strict,
            },
        }

    def to_anthropic_tool(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


@dataclass(slots=True)
class PlanStep:
    step_id: str
    title: str
    description: str
    kind: StepKind = StepKind.ANALYZE
    depends_on: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    suggested_tools: List[str] = field(default_factory=list)
    risk_notes: List[str] = field(default_factory=list)
    estimated_cost: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload


@dataclass(slots=True)
class Plan:
    goal: str
    assumptions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    steps: List[PlanStep] = field(default_factory=list)
    deliverables: List[str] = field(default_factory=list)

    def step_index(self) -> Dict[str, PlanStep]:
        return {step.step_id: step for step in self.steps}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "assumptions": list(self.assumptions),
            "constraints": list(self.constraints),
            "steps": [step.to_dict() for step in self.steps],
            "deliverables": list(self.deliverables),
        }

    def to_pretty_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass(slots=True)
class TodoItem:
    todo_id: str
    content: str
    active_form: str
    linked_step_id: Optional[str] = None
    status: TodoStatus = TodoStatus.PENDING
    owner: str = "agent"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "todo_id": self.todo_id,
            "content": self.content,
            "active_form": self.active_form,
            "linked_step_id": self.linked_step_id,
            "status": self.status.value,
            "owner": self.owner,
            "notes": self.notes,
        }


@dataclass(slots=True)
class SkillContext:
    name: str
    description: str
    success_definition: List[str] = field(default_factory=list)
    planning_hints: List[str] = field(default_factory=list)
    extra_instructions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentTurn:
    objective: str
    plan: Plan
    todos: List[TodoItem]
    observations: List[str] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    blocked_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "plan": self.plan.to_dict(),
            "todos": [todo.to_dict() for todo in self.todos],
            "observations": list(self.observations),
            "completed_steps": list(self.completed_steps),
            "blocked_steps": list(self.blocked_steps),
        }
