from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from agent_memory_os import ToolSchema
from agent_tools import AgentSessionState, ToolContext, ToolResult


ToolHandler = Callable[[dict[str, Any], ToolContext, AgentSessionState, int], Any]


def serialize_tool_output(value: Any) -> Any:
    if isinstance(value, ToolResult):
        return {
            "ok": value.ok,
            "tool": value.tool.value,
            "summary": value.summary,
            "data": value.data,
            "warnings": [
                {
                    "code": item.code,
                    "message": item.message,
                    "risk": item.risk.value,
                }
                for item in value.warnings
            ],
            "audit_id": value.audit_id,
        }
    return value


@dataclass(slots=True)
class RuntimeTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    strict: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters_json_schema=self.parameters,
        )


@dataclass(slots=True)
class SessionAwareToolExecutor:
    tools: list[RuntimeTool]
    ctx: ToolContext
    state: AgentSessionState = field(default_factory=AgentSessionState)
    _tool_map: dict[str, RuntimeTool] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._tool_map = {tool.name: tool for tool in self.tools}

    def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in self._tool_map:
            raise KeyError(f"Unknown tool: {name}")
        call_count = self.state.register_call(name, arguments)
        tool = self._tool_map[name]
        return tool.handler(arguments, self.ctx, self.state, call_count)

    def schemas(self) -> list[ToolSchema]:
        return [tool.to_schema() for tool in self.tools]

    def list_tools(self) -> list[RuntimeTool]:
        return list(self.tools)
