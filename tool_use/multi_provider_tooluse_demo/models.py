from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

JSONDict = Dict[str, Any]


@dataclass(frozen=True)
class ToolSpec:
    """Provider-agnostic tool definition."""

    name: str
    description: str
    parameters: JSONDict
    strict: bool = True


@dataclass(frozen=True)
class ToolCall:
    """Normalized tool call returned by a model."""

    call_id: str
    name: str
    arguments_json: str
    arguments: JSONDict


@dataclass(frozen=True)
class ToolExecutionResult:
    """Normalized tool result produced by local code."""

    call_id: str
    name: str
    output: Any
    is_error: bool = False

    def as_text(self) -> str:
        if isinstance(self.output, str):
            return self.output
        import json

        return json.dumps(self.output, ensure_ascii=False)


@dataclass
class NormalizedResponse:
    """Provider-agnostic model response."""

    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: Optional[str] = None
    raw_assistant_message: Any = None
    raw_response: Any = None
    response_id: Optional[str] = None

    @property
    def needs_tool_execution(self) -> bool:
        return len(self.tool_calls) > 0
