from __future__ import annotations

from dataclasses import dataclass
import json
import urllib.request

from multi_vendor_skills.models import SkillDefinition
from multi_vendor_skills.renderers.openai_tools import OpenAICompatibleToolsRenderer, DeepSeekToolsRenderer


@dataclass(slots=True)
class OpenAICompatibleRuntime:
    base_url: str
    api_key: str
    model: str
    provider: str = "generic-openai"
    timeout_seconds: int = 120

    def _build_tools(self, skill: SkillDefinition) -> list[dict]:
        if self.provider == "deepseek":
            return DeepSeekToolsRenderer().function_object(skill)
        return OpenAICompatibleToolsRenderer().function_object(skill)

    def _chat_completion(self, payload: dict) -> dict:
        url = self.base_url.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def invoke(self, skill: SkillDefinition, user_prompt: str, max_rounds: int = 6) -> dict:
        skill.validate()
        tools = self._build_tools(skill)
        messages: list[dict] = [
            {"role": "system", "content": skill.instructions.strip()},
            {"role": "user", "content": user_prompt},
        ]
        executors = {tool.name: tool.executor for tool in skill.tools if tool.executor is not None}

        for _ in range(max_rounds):
            payload = {
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0,
            }
            response = self._chat_completion(payload)
            message = response["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []
            messages.append(message)

            if not tool_calls:
                return response

            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                raw_arguments = tool_call["function"].get("arguments") or "{}"
                arguments = json.loads(raw_arguments)
                executor = executors.get(tool_name)
                if executor is None:
                    tool_result = {"error": f"No local executor registered for {tool_name}"}
                else:
                    try:
                        tool_result = executor(arguments)
                    except Exception as exc:  # pragma: no cover - example runtime
                        tool_result = {"error": f"{type(exc).__name__}: {exc}"}

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

        raise RuntimeError(f"Tool loop exceeded max_rounds={max_rounds}")
