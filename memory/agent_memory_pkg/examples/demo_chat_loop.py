from __future__ import annotations

from agent_memory import HierarchicalMemoryManager, Message, MessageRole


def main() -> None:
    manager = HierarchicalMemoryManager(namespace="demo/chat", compaction_trigger_messages=10)
    manager.set_system_instructions(
        [
            "You are a coding agent with hierarchical memory.",
            "Keep stable content first for provider cache hit maximization.",
        ]
    )
    manager.pin_instruction("Never drop hard user constraints.")

    turns = [
        (MessageRole.USER, "Remember that my preference is typed Python and small functions."),
        (MessageRole.ASSISTANT, "Got it. I will prefer typed Python and small functions."),
        (MessageRole.USER, "Our stack uses DeepSeek for cheap batch jobs."),
        (MessageRole.ASSISTANT, "Noted. DeepSeek is part of your provider mix."),
        (MessageRole.USER, "Decision: keep tool definitions stable at the prompt prefix."),
        (MessageRole.ASSISTANT, "Agreed. That reduces cache churn."),
        (MessageRole.USER, "Next step: add Anthropic and Kimi adapters."),
        (MessageRole.ASSISTANT, "I will add adapters and keep their cache semantics separate."),
        (MessageRole.USER, "Environment: project is multi-tenant and needs namespace isolation."),
        (MessageRole.ASSISTANT, "Understood. I will namespace both memory and cache keys."),
        (MessageRole.USER, "Artifact: wrote provider registry and payload builders."),
        (MessageRole.ASSISTANT, "Great. I will keep that artifact in episodic memory."),
    ]

    for role, content in turns:
        manager.ingest_message(Message(role=role, content=content))

    print("=== MEMORY SNAPSHOT AFTER AUTO-COMPACTION ===")
    state = manager.export_state()
    for memory in state["memories"]:
        print(memory)

    print("\n=== OPENAI REQUEST ===")
    request = manager.prepare_request(
        provider_name="openai",
        model="gpt-5.4",
        user_message="Implement the remaining provider adapters and preserve memory continuity.",
    )
    print(request.pretty_json())


if __name__ == "__main__":
    main()
