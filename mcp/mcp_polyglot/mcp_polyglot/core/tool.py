from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


JSON = Dict[str, Any]


@dataclass(slots=True)
class ToolAnnotations:
    title: Optional[str] = None
    read_only_hint: Optional[bool] = None
    destructive_hint: Optional[bool] = None
    idempotent_hint: Optional[bool] = None
    open_world_hint: Optional[bool] = None

    def to_mcp_dict(self) -> JSON:
        data: JSON = {}
        if self.title is not None:
            data["title"] = self.title
        if self.read_only_hint is not None:
            data["readOnlyHint"] = self.read_only_hint
        if self.destructive_hint is not None:
            data["destructiveHint"] = self.destructive_hint
        if self.idempotent_hint is not None:
            data["idempotentHint"] = self.idempotent_hint
        if self.open_world_hint is not None:
            data["openWorldHint"] = self.open_world_hint
        return data


@dataclass(slots=True)
class TextContent:
    text: str
    type: str = "text"

    def to_mcp_dict(self) -> JSON:
        return {"type": self.type, "text": self.text}


@dataclass(slots=True)
class ToolCallResult:
    content: List[TextContent]
    is_error: bool = False
    structured_content: Optional[JSON] = None

    def to_mcp_dict(self) -> JSON:
        data: JSON = {
            "content": [item.to_mcp_dict() for item in self.content],
            "isError": self.is_error,
        }
        if self.structured_content is not None:
            data["structuredContent"] = self.structured_content
        return data

    def to_provider_text(self) -> str:
        if self.structured_content is not None:
            return str(self.structured_content)
        return "\n".join(item.text for item in self.content)


class BaseMcpTool(ABC):
    """
    标准 MCP Tool 抽象基类。
    """

    name: str
    title: Optional[str]
    description: str
    input_schema: JSON
    annotations: Optional[ToolAnnotations]

    def __init__(
        self,
        *,
        name: str,
        description: str,
        input_schema: JSON,
        title: Optional[str] = None,
        annotations: Optional[ToolAnnotations] = None,
    ) -> None:
        self.name = name
        self.title = title
        self.description = description
        self.input_schema = input_schema
        self.annotations = annotations

    def to_mcp_tool_definition(self) -> JSON:
        payload: JSON = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.title:
            payload["title"] = self.title
        if self.annotations:
            ann = self.annotations.to_mcp_dict()
            if ann:
                payload["annotations"] = ann
        return payload

    def to_openai_compatible_function(self) -> JSON:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    @abstractmethod
    def call(self, arguments: JSON) -> ToolCallResult:
        raise NotImplementedError
