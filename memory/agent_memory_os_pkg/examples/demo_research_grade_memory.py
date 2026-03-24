from __future__ import annotations

from pathlib import Path

from agent_memory_os import AgentMemoryOS, ClaudeCodeMemoryExporter, Message, MessageRole, ToolSchema


def main() -> None:
    osys = AgentMemoryOS(namespace="demo")
    osys.set_system_policies([
        "You are a production coding agent.",
        "Keep the stable prefix canonical and unchanged unless rules genuinely change.",
    ])
    osys.add_user_instruction("Always preserve user constraints and prefer concise typed Python.")
    osys.register_tools([
        ToolSchema(
            name="search_docs",
            description="Search docs",
            parameters_json_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        ToolSchema(
            name="run_tests",
            description="Run the test suite",
            parameters_json_schema={"type": "object", "properties": {}, "required": []},
        ),
    ])

    turns = [
        Message(role=MessageRole.USER, content="Remember that I prefer concise typed Python and minimal diffs."),
        Message(role=MessageRole.ASSISTANT, content="Understood. I will prefer concise typed Python and minimal diffs."),
        Message(role=MessageRole.USER, content="We use poetry and pytest in this repo."),
        Message(role=MessageRole.TOOL, content="artifact: /workspace/pyproject.toml and /workspace/tests/test_memory.py"),
        Message(role=MessageRole.ASSISTANT, content="decision: use a block-DAG control plane and reversible compaction."),
        Message(role=MessageRole.USER, content="next step: add OpenAI and Anthropic provider runtimes."),
    ]
    for msg in turns:
        osys.observe(msg)

    request = osys.prepare_request(
        provider_name="anthropic",
        model="claude-opus-4-6",
        user_message="Implement a cache-safe memory operating system for agents.",
        extra={"enable_compaction": True, "cache_ttl": "1h"},
    )
    print(request.pretty_json())

    out = Path("/tmp/claude_code_demo")
    exporter = ClaudeCodeMemoryExporter()
    paths = exporter.export(out, osys.control_blocks(), osys.all_blocks())
    print(paths)


if __name__ == "__main__":
    main()
