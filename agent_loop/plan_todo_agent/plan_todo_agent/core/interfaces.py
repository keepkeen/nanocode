from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .schemas import AgentTurn, Plan, SkillContext, TodoItem, ToolSpec


class BaseProviderAdapter(ABC):
    """Boundary adapter that isolates provider-specific payload shapes."""

    name: str

    @abstractmethod
    def build_request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: List[ToolSpec],
        turn: Optional[AgentTurn] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def format_capabilities(self) -> Dict[str, Any]:
        raise NotImplementedError


class BaseSkill(ABC):
    """Skill contract: domain-specific knowledge without provider coupling."""

    @property
    @abstractmethod
    def context(self) -> SkillContext:
        raise NotImplementedError

    @abstractmethod
    def build_tools(self) -> List[ToolSpec]:
        raise NotImplementedError

    @abstractmethod
    def bootstrap_plan(self, objective: str) -> Plan:
        raise NotImplementedError


class BasePlanCritic(ABC):
    @abstractmethod
    def review(self, plan: Plan, tools: List[ToolSpec]) -> List[str]:
        raise NotImplementedError


class BaseTodoProjector(ABC):
    @abstractmethod
    def project(self, plan: Plan, completed_steps: List[str], blocked_steps: List[str]) -> List[TodoItem]:
        raise NotImplementedError
