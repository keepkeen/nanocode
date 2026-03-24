from __future__ import annotations

from dataclasses import dataclass
import json
import urllib.request

from multi_vendor_skills.models import SkillDefinition
from multi_vendor_skills.renderers.anthropic_tools import AnthropicToolsRenderer


@dataclass(slots=True)
class AnthropicCompatibleRuntime:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 120
    anthropic_version: str = "2023-06-01"

    def _messages(self, payload: dict) -> dict:
        url = self.base_url.rstrip("/") + "/messages"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.anthropic_version,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def invoke(self, skill: SkillDefinition, user_prompt: str, max_rounds: int = 6) -> dict:
        skill.validate()
        tools = json.loads(AnthropicToolsRenderer().render(skill)[0].content.decode("utf-8"))
        executors = {tool.name: tool.executor for tool in skill.tools if tool.executor is not None}
        messages: list[dict] = [
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]}
        ]

        for _ in range(max_rounds):
            payload = {
                "model": self.model,
                "system": skill.instructions.strip(),
                "max_tokens": 1024,
                "messages": messages,
                "tools": tools,
            }
            response = self._messages(payload)
            content_blocks = response.get("content") or []
            messages.append({"role": "assistant", "content": content_blocks})

            tool_uses = [block for block in content_blocks if block.get("type") == "tool_use"]
            if not tool_uses:
                return response

            for block in tool_uses:
                name = block["name"]
                executor = executors.get(name)
                if executor is None:
                    result = {"error": f"No local executor registered for {name}"}
                else:
                    try:
                        result = executor(block.get("input") or {})
                    except Exception as exc:  # pragma: no cover - example runtime
                        result = {"error": f"{type(exc).__name__}: {exc}"}

                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": block["id"],
                                "content": json.dumps(result, ensure_ascii=False),
                            }
                        ],
                    }
                )

        raise RuntimeError(f"Tool loop exceeded max_rounds={max_rounds}")
