from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models import JSONDict, NormalizedResponse, ToolExecutionResult, ToolSpec


@dataclass
class ConversationState:
    request_tools: List[JSONDict]
    extra: Dict[str, Any] = field(default_factory=dict)


class ProviderAdapter(ABC):
    provider_name: str
    model: str

    def __init__(self, model: str):
        self.model = model

    @abstractmethod
    def base_url(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def path(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def headers(self, api_key: str) -> Dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def start_state(self, user_prompt: str, tools: List[ToolSpec]) -> ConversationState:
        raise NotImplementedError

    @abstractmethod
    def build_request(self, state: ConversationState) -> JSONDict:
        raise NotImplementedError

    @abstractmethod
    def parse_response(self, data: JSONDict) -> NormalizedResponse:
        raise NotImplementedError

    @abstractmethod
    def apply_tool_results(
        self,
        state: ConversationState,
        response: NormalizedResponse,
        tool_results: List[ToolExecutionResult],
    ) -> None:
        raise NotImplementedError

    def url(self) -> str:
        return self.base_url().rstrip("/") + self.path()

    def serialize_tools(self, tools: List[ToolSpec]) -> List[JSONDict]:
        return [self.serialize_tool(tool) for tool in tools]

    @abstractmethod
    def serialize_tool(self, tool: ToolSpec) -> JSONDict:
        raise NotImplementedError

    def default_system_prompt(self) -> Optional[str]:
        return None
