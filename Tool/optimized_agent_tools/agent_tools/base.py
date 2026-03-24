from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import ToolContext, ToolResult


class AgentTool(ABC):
    name: str

    @abstractmethod
    def invoke(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        raise NotImplementedError


class SearchProvider(ABC):
    provider_name: str

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ):
        raise NotImplementedError


class FetchProvider(ABC):
    provider_name: str

    @abstractmethod
    def fetch(self, url: str):
        raise NotImplementedError


class SandboxAdapter(ABC):
    name: str = "none"

    @abstractmethod
    def wrap(self, argv: list[str], cwd: str, env: dict[str, str]) -> tuple[list[str], str, dict[str, str]]:
        raise NotImplementedError
