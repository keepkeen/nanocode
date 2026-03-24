from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import hashlib
import json

from .base import AgentTool
from .cache import TTLCache
from .types import ToolContext, ToolResult


@dataclass
class AgentSessionState:
    seen_urls: set[str] = field(default_factory=set)
    repeated_calls: dict[str, int] = field(default_factory=dict)
    cache: TTLCache[Any] = field(default_factory=lambda: TTLCache(ttl_seconds=900, max_items=256))

    def remember_urls(self, urls: list[str]) -> None:
        self.seen_urls.update(urls)

    def is_url_known(self, url: str) -> bool:
        return url in self.seen_urls

    def register_call(self, tool_name: str, payload: dict[str, Any]) -> int:
        key = hashlib.sha256(json.dumps({"tool": tool_name, "payload": payload}, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        self.repeated_calls[key] = self.repeated_calls.get(key, 0) + 1
        return self.repeated_calls[key]


class ToolRegistry:
    def __init__(self, state: AgentSessionState | None = None) -> None:
        self.state = state or AgentSessionState()
        self.tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self.tools[tool.name] = tool

    def invoke(self, tool_name: str, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        tool = self.tools[tool_name]
        count = self.state.register_call(tool_name, kwargs)
        kwargs = dict(kwargs)
        kwargs["session_state"] = self.state
        kwargs["call_count"] = count
        return tool.invoke(ctx, **kwargs)
