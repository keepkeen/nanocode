from __future__ import annotations

from agent_memory_os import AgentMemoryOS, Message, MessageRole, ToolSchema
from agent_memory_os.providers import AnthropicRuntime, OpenAICompatibleRuntime, OpenAIRuntime


def build_os() -> AgentMemoryOS:
    osys = AgentMemoryOS(namespace="providers")
    osys.set_system_policies([
        "You are a robust software engineering agent.",
        "Do not break the stable prefix unless control-plane rules changed.",
    ])
    osys.observe(Message(role=MessageRole.USER, content="I prefer terse answers and typed Python."))
    osys.observe(Message(role=MessageRole.USER, content="Our repo uses uv and pytest."))
    osys.register_tools([
        ToolSchema(
            name="grep_code",
            description="Search source code",
            parameters_json_schema={
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        )
    ])
    return osys


def main() -> None:
    osys = build_os()

    payloads = {
        "openai_responses": osys.prepare_request(provider_name="openai_responses", model="gpt-5.4", user_message="Design the memory layer."),
        "deepseek": osys.prepare_request(provider_name="deepseek", model="deepseek-chat", user_message="Design the memory layer."),
        "glm": osys.prepare_request(provider_name="glm", model="glm-4.7", user_message="Design the memory layer."),
        "kimi": osys.prepare_request(provider_name="kimi", model="kimi-k2.5", user_message="Design the memory layer.", extra={"cache_id": "cache-example", "reset_ttl": 3600}),
        "minimax": osys.prepare_request(provider_name="minimax", model="MiniMax-M2.7", user_message="Design the memory layer."),
        "anthropic": osys.prepare_request(provider_name="anthropic", model="claude-opus-4-6", user_message="Design the memory layer."),
    }

    for name, req in payloads.items():
        print("=" * 80)
        print(name)
        print(req.pretty_json())

    # The following runtime examples are commented out because they require API keys and network access.
    # openai_runtime = OpenAIRuntime()
    # resp = openai_runtime.invoke(payloads["openai_responses"], api_key="sk-...", base_url="https://api.openai.com/v1")
    # print(resp)

    # anthropic_runtime = AnthropicRuntime()
    # resp = anthropic_runtime.invoke(payloads["anthropic"], api_key="sk-ant-...", base_url="https://api.anthropic.com")
    # print(resp)

    # compat_runtime = OpenAICompatibleRuntime()
    # resp = compat_runtime.invoke(payloads["deepseek"], api_key="...", base_url="https://api.deepseek.com")
    # print(resp)


if __name__ == "__main__":
    main()
