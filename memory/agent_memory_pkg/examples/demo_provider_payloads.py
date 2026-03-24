from __future__ import annotations

import json

from agent_memory import HierarchicalMemoryManager, Message, MessageRole
from agent_memory.models import ToolSchema
from agent_memory.claude_code_memory import ClaudeCodeProjectMemory


def build_manager() -> HierarchicalMemoryManager:
    manager = HierarchicalMemoryManager(namespace="fxcove/research")
    manager.set_system_instructions(
        [
            "You are an agent memory subsystem inside a coding agent.",
            "Keep the stable prefix deterministic and move dynamic content to the tail.",
            "Prefer concise typed Python and preserve user constraints across turns.",
        ]
    )
    manager.pin_instruction("Always preserve pinned constraints even after compaction.")
    manager.register_tools(
        [
            ToolSchema(
                name="search_web",
                description="Search the web for recent information.",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            ),
            ToolSchema(
                name="open_repo_file",
                description="Read a repository file.",
                parameters_json_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
        ]
    )
    seed_turns = [
        (MessageRole.USER, "Remember that I prefer concise code and typed Python."),
        (MessageRole.ASSISTANT, "Noted. I will prefer concise code and typed Python."),
        (MessageRole.USER, "Our stack uses OpenAI, Kimi, DeepSeek, and Claude for different tasks."),
        (MessageRole.ASSISTANT, "Understood. I will keep provider-specific differences in mind."),
        (MessageRole.USER, "Decision: stable tool schemas should not move between turns."),
        (MessageRole.ASSISTANT, "Agreed. Stable tool schemas belong in the prefix."),
        (MessageRole.USER, "Next step: implement a provider-agnostic memory manager."),
        (MessageRole.ASSISTANT, "I will build a modular design with adapters and a compressor."),
    ]
    for role, content in seed_turns:
        manager.ingest_message(Message(role=role, content=content))
    return manager


def main() -> None:
    manager = build_manager()
    user_goal = "Implement cache-friendly memory retention for long-running agent conversations."
    providers = {
        "openai": "gpt-5.4",
        "deepseek": "deepseek-chat",
        "glm": "glm-4.7",
        "minimax": "MiniMax-M2.7",
        "kimi": "kimi-k2.5",
        "anthropic": "claude-sonnet-4-6",
    }
    print("=== PROVIDER PAYLOADS ===")
    for provider_name, model in providers.items():
        request = manager.prepare_request(provider_name=provider_name, model=model, user_message=user_goal)
        print(f"\n--- {provider_name.upper()} ---")
        print(request.pretty_json())

    print("\n=== CLAUDE CODE FILE EXPORT ===")
    project_memory = ClaudeCodeProjectMemory(
        project_name="fxcove-agent-memory",
        coding_rules=[
            "Use typed Python.",
            "Do not rewrite stable prefix content during compaction.",
        ],
        workflow_rules=[
            "Run tests after changing provider adapters.",
            "Keep dynamic tool results out of the stable prefix.",
        ],
        memories=manager.store.list_memories(manager.namespace),
    )
    print(project_memory.render_claude_md())
    print(project_memory.render_memory_md())

    print("\n=== STATE SNAPSHOT ===")
    print(json.dumps(manager.export_state(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
