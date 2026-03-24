from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable

from .models import ToolSpec


class BaseTool(ABC):
    """Abstract local tool implementation."""

    @property
    @abstractmethod
    def spec(self) -> ToolSpec:
        raise NotImplementedError

    @abstractmethod
    def execute(self, arguments: Dict[str, Any]) -> Any:
        raise NotImplementedError


class ToolRegistry:
    def __init__(self, tools: Iterable[BaseTool]):
        self._tools = {tool.spec.name: tool for tool in tools}

    def specs(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values()]

    def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name].execute(arguments)


class GetWeatherTool(BaseTool):
    """Demo tool.

    This uses local stub data on purpose so the example can run end-to-end
    without introducing a second external dependency.
    Replace the execute() body with a real weather API call in production.
    """

    _WEATHER = {
        "beijing": {"location": "Beijing", "temperature_c": 22, "condition": "Sunny"},
        "hangzhou": {"location": "Hangzhou", "temperature_c": 24, "condition": "Cloudy"},
        "san francisco": {"location": "San Francisco", "temperature_c": 16, "condition": "Foggy"},
        "shanghai": {"location": "Shanghai", "temperature_c": 20, "condition": "Rainy"},
    }

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="get_weather",
            description="Get the current weather in a given location.",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name, such as Beijing or San Francisco.",
                    }
                },
                "required": ["location"],
                "additionalProperties": False,
            },
            strict=True,
        )

    def execute(self, arguments: Dict[str, Any]) -> Any:
        location = str(arguments.get("location", "")).strip()
        if not location:
            return {"error": "location is required"}
        key = location.lower()
        return self._WEATHER.get(
            key,
            {"location": location, "temperature_c": 21, "condition": "Unknown / demo stub"},
        )
