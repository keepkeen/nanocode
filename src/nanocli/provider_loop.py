from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json

from agent_memory_os import Message, MessageRole, ProviderRequest

from .models import ModelProfile
from .models import TraceKind
from .storage import LocalStateStore


@dataclass(slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ToolExecution:
    call_id: str
    name: str
    output: Any
    is_error: bool = False

    def as_text(self) -> str:
        if isinstance(self.output, str):
            return self.output
        return json.dumps(self.output, ensure_ascii=False)


@dataclass(slots=True)
class ToolLoopResult:
    response: dict[str, Any]
    final_text: str
    rounds: int


class ProviderToolLoop:
    def __init__(
        self,
        *,
        profile: ModelProfile,
        run_id: str,
        session_id: str | None = None,
        store: LocalStateStore,
        invoke_provider,
        tool_registry,
        memory,
        on_tool_observation=None,
    ) -> None:
        self.profile = profile
        self.run_id = run_id
        self.session_id = session_id
        self.store = store
        self.invoke_provider = invoke_provider
        self.tool_registry = tool_registry
        self.memory = memory
        self.on_tool_observation = on_tool_observation

    def run(self, request: ProviderRequest, *, api_key: str, max_rounds: int = 6) -> ToolLoopResult:
        current = request
        final_response: dict[str, Any] | None = None
        final_text = ""
        for round_index in range(1, max_rounds + 1):
            request_payload = self._request_dict(current)
            request_artifact = self.store.save_artifact(self.run_id, f"provider_request_round_{round_index}", request_payload)
            self.store.append_trace(
                self.run_id,
                kind=TraceKind.PROVIDER_REQUEST,
                message=f"provider request round {round_index}",
                payload={"provider": current.provider.value, "endpoint_style": current.endpoint_style},
                artifact_path=request_artifact,
            )
            response_raw = self.invoke_provider(current, self.profile, api_key)
            response = self._coerce_json(response_raw)
            response_artifact = self.store.save_artifact(self.run_id, f"provider_response_round_{round_index}", response)
            summary_text = self.extract_text(current, response)
            self.store.append_trace(
                self.run_id,
                kind=TraceKind.PROVIDER_RESPONSE,
                message=f"provider response round {round_index}",
                payload={"provider": current.provider.value, "text_preview": summary_text[:200]},
                artifact_path=response_artifact,
            )
            self.store.append_provider_call(
                self.run_id,
                session_id=self.session_id,
                provider=current.provider.value,
                model=self.profile.model,
                endpoint_style=current.endpoint_style,
                status="completed",
                request_artifact_path=request_artifact,
                response_artifact_path=response_artifact,
                summary=(summary_text or "tool round completed")[:500],
            )
            final_response = response
            final_text = summary_text

            tool_calls = self.parse_tool_calls(current, response)
            if not tool_calls:
                break

            executions: list[ToolExecution] = []
            for tool_call in tool_calls:
                try:
                    output = self.tool_registry.execute(tool_call.name, tool_call.arguments)
                    executions.append(ToolExecution(call_id=tool_call.call_id, name=tool_call.name, output=output, is_error=False))
                except Exception as exc:  # pragma: no cover - defensive
                    executions.append(ToolExecution(call_id=tool_call.call_id, name=tool_call.name, output={"error": str(exc)}, is_error=True))
                payload = {
                    "call_id": tool_call.call_id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                }
                result_payload = {
                    "output": executions[-1].output,
                    "is_error": executions[-1].is_error,
                }
                artifact = self.store.save_artifact(
                    self.run_id,
                    f"tool_{round_index}_{tool_call.name}_{tool_call.call_id[:8]}",
                    {"request": payload, "result": result_payload},
                )
                self.store.append_tool_call(
                    self.run_id,
                    session_id=self.session_id,
                    tool_name=tool_call.name,
                    call_id=tool_call.call_id,
                    ok=not executions[-1].is_error,
                    payload=payload,
                    result=result_payload,
                    artifact_path=artifact,
                )
                self.store.append_trace(
                    self.run_id,
                    kind=TraceKind.TOOL,
                    message=f"executed tool {tool_call.name}",
                    payload={"call_id": tool_call.call_id, "ok": not executions[-1].is_error},
                    artifact_path=artifact,
                )
                observation = Message(
                    role=MessageRole.TOOL,
                    content=f"{tool_call.name}: {executions[-1].as_text()}",
                    metadata={"tool_name": tool_call.name, "tool_call_id": tool_call.call_id},
                )
                if self.on_tool_observation is not None:
                    self.on_tool_observation(tool_call, executions[-1], observation)
                else:
                    self.memory.observe(observation)

            current = self.apply_tool_results(current, response, executions)
        else:
            raise RuntimeError(f"tool loop did not finish within {max_rounds} rounds")

        if final_response is None:
            raise RuntimeError("provider returned no response")
        return ToolLoopResult(response=final_response, final_text=final_text, rounds=round_index)

    @staticmethod
    def _coerce_json(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        if hasattr(value, "to_dict"):
            dumped = value.to_dict()
            if isinstance(dumped, dict):
                return dumped
        if isinstance(value, dict):
            return value
        if hasattr(value, "__dict__"):
            return json.loads(json.dumps(value.__dict__, ensure_ascii=False, default=str))
        return {"value": str(value)}

    @staticmethod
    def _request_dict(request: ProviderRequest) -> dict[str, Any]:
        return {
            "provider": request.provider.value,
            "endpoint_style": request.endpoint_style,
            "path": request.path,
            "payload": request.payload,
            "headers": request.headers,
            "diagnostics": request.diagnostics,
        }

    def parse_tool_calls(self, request: ProviderRequest, response: dict[str, Any]) -> list[ToolCall]:
        if request.endpoint_style == "responses":
            tool_calls: list[ToolCall] = []
            for item in response.get("output", []):
                if item.get("type") == "function_call":
                    args_json = item.get("arguments", "{}")
                    tool_calls.append(
                        ToolCall(
                            call_id=item["call_id"],
                            name=item["name"],
                            arguments=json.loads(args_json),
                        )
                    )
            return tool_calls

        if request.endpoint_style == "chat.completions":
            choices = response.get("choices")
            if choices:
                message = choices[0].get("message", {})
                tool_calls = []
                for item in message.get("tool_calls") or []:
                    tool_calls.append(
                        ToolCall(
                            call_id=item["id"],
                            name=item["function"]["name"],
                            arguments=json.loads(item["function"]["arguments"]),
                        )
                    )
                return tool_calls

        if request.endpoint_style in {"messages", "anthropic-compatible"}:
            tool_calls = []
            for block in response.get("content", []):
                if block.get("type") == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            call_id=block["id"],
                            name=block["name"],
                            arguments=block.get("input", {}),
                        )
                    )
            return tool_calls
        return []

    def apply_tool_results(self, request: ProviderRequest, response: dict[str, Any], executions: list[ToolExecution]) -> ProviderRequest:
        payload = dict(request.payload)
        if request.endpoint_style == "responses":
            payload["previous_response_id"] = response.get("id")
            payload["input"] = [
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": item.as_text(),
                }
                for item in executions
            ]
            return ProviderRequest(
                provider=request.provider,
                endpoint_style=request.endpoint_style,
                path=request.path,
                payload=payload,
                headers=request.headers,
                diagnostics=request.diagnostics,
            )

        if request.endpoint_style == "chat.completions":
            choices = response.get("choices")
            if not choices:
                return request
            assistant_message = choices[0].get("message", {})
            messages = list(payload.get("messages", []))
            messages.append(assistant_message)
            for item in executions:
                tool_message = {
                    "role": "tool",
                    "tool_call_id": item.call_id,
                    "content": item.as_text(),
                }
                if self.profile.provider == "kimi":
                    tool_message["name"] = item.name
                messages.append(tool_message)
            payload["messages"] = messages
            return ProviderRequest(
                provider=request.provider,
                endpoint_style=request.endpoint_style,
                path=request.path,
                payload=payload,
                headers=request.headers,
                diagnostics=request.diagnostics,
            )

        if request.endpoint_style in {"messages", "anthropic-compatible"}:
            messages = list(payload.get("messages", []))
            messages.append({"role": "assistant", "content": response.get("content", [])})
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": item.call_id,
                            "is_error": item.is_error,
                            "content": item.as_text(),
                        }
                        for item in executions
                    ],
                }
            )
            payload["messages"] = messages
            return ProviderRequest(
                provider=request.provider,
                endpoint_style=request.endpoint_style,
                path=request.path,
                payload=payload,
                headers=request.headers,
                diagnostics=request.diagnostics,
            )
        return request

    def extract_text(self, request: ProviderRequest, response: dict[str, Any]) -> str:
        if request.endpoint_style == "responses":
            chunks: list[str] = []
            for item in response.get("output", []):
                if item.get("type") == "message":
                    for block in item.get("content", []):
                        if block.get("type") in {"output_text", "text"}:
                            chunks.append(block.get("text", ""))
            return "".join(chunks).strip()
        if request.endpoint_style == "chat.completions":
            choices = response.get("choices")
            if choices:
                message = choices[0].get("message", {})
                content = message.get("content")
                return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        if request.endpoint_style in {"messages", "anthropic-compatible"}:
            return "".join(block.get("text", "") for block in response.get("content", []) if block.get("type") == "text").strip()
        return ""
