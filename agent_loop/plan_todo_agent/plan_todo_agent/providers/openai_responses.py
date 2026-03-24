from __future__ import annotations

from typing import Any, Dict, List, Optional

from plan_todo_agent.core.interfaces import BaseProviderAdapter
from plan_todo_agent.core.schemas import AgentTurn, ToolSpec


class OpenAIResponsesAdapter(BaseProviderAdapter):
    name = "openai-responses"

    def __init__(
        self,
        *,
        model: str = "gpt-5",
        reasoning_effort: str = "medium",
        reasoning_summary: str = "concise",
        parallel_tool_calls: bool = False,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.reasoning_summary = reasoning_summary
        self.parallel_tool_calls = parallel_tool_calls

    def build_request(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: List[ToolSpec],
        turn: Optional[AgentTurn] = None,
    ) -> Dict[str, Any]:
        input_items: List[Dict[str, Any]] = [
            {
                "role": "developer",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ]
        return {
            "model": self.model,
            "reasoning": {
                "effort": self.reasoning_effort,
                "summary": self.reasoning_summary,
            },
            "parallel_tool_calls": self.parallel_tool_calls,
            "input": input_items,
            "tools": [tool.to_openai_tool() for tool in tools],
        }

    def parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        output = response.get("output", [])
        parsed: Dict[str, Any] = {
            "text": response.get("output_text", ""),
            "function_calls": [],
            "reasoning": [],
        }
        for item in output:
            item_type = item.get("type")
            if item_type == "function_call":
                parsed["function_calls"].append(
                    {
                        "call_id": item.get("call_id"),
                        "name": item.get("name"),
                        "arguments": item.get("arguments"),
                    }
                )
            elif item_type == "reasoning":
                parsed["reasoning"].append(item)
        return parsed

    def format_capabilities(self) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "api_style": "responses",
            "reasoning": "native",
            "tool_use": "function tools + MCP + built-in tools",
        }
