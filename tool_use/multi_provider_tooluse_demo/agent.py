from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional

from .adapters.base import ProviderAdapter
from .models import NormalizedResponse, ToolExecutionResult
from .tools import ToolRegistry
from .transports import Transport


@dataclass
class ToolLoopResult:
    final_response: NormalizedResponse
    turns: List[NormalizedResponse]


class ToolUseAgent:
    """Provider-independent tool-use loop.

    The adapter owns all protocol differences. The agent owns the common loop:
    1) send request, 2) parse tool calls, 3) execute tools, 4) send tool results,
    5) stop when the model returns plain text without new tool calls.
    """

    def __init__(self, provider: ProviderAdapter, transport: Transport, api_key: str, registry: ToolRegistry):
        self.provider = provider
        self.transport = transport
        self.api_key = api_key
        self.registry = registry

    def run(self, prompt: str, max_rounds: int = 8) -> ToolLoopResult:
        state = self.provider.start_state(prompt, self.registry.specs())
        turns: List[NormalizedResponse] = []

        for _ in range(max_rounds):
            request_body = self.provider.build_request(state)
            response_json = self.transport.post(
                url=self.provider.url(),
                headers=self.provider.headers(self.api_key),
                json_body=request_body,
            )
            normalized = self.provider.parse_response(response_json)
            turns.append(normalized)

            if not normalized.needs_tool_execution:
                return ToolLoopResult(final_response=normalized, turns=turns)

            tool_results: List[ToolExecutionResult] = []
            for tool_call in normalized.tool_calls:
                try:
                    output = self.registry.execute(tool_call.name, tool_call.arguments)
                    tool_results.append(
                        ToolExecutionResult(
                            call_id=tool_call.call_id,
                            name=tool_call.name,
                            output=output,
                            is_error=False,
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive path
                    tool_results.append(
                        ToolExecutionResult(
                            call_id=tool_call.call_id,
                            name=tool_call.name,
                            output={"error": str(exc)},
                            is_error=True,
                        )
                    )

            self.provider.apply_tool_results(state, normalized, tool_results)

        raise RuntimeError(f"Tool loop did not finish in {max_rounds} rounds")
