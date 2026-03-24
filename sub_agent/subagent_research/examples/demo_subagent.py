from __future__ import annotations

import asyncio
import json
from pathlib import Path

from subagent_framework.agents import ResearchSubAgent
from subagent_framework.models import TaskEnvelope
from subagent_framework.orchestrator import SubAgentOrchestrator, SubAgentRegistry
from subagent_framework.providers import (
    ClaudeCodeAdapter,
    DeepSeekAdapter,
    GLMAdapter,
    KimiAdapter,
    MiniMaxAdapter,
    OpenAIChatGPTAdapter,
)


async def main() -> None:
    registry = SubAgentRegistry()
    research_agent = ResearchSubAgent()
    registry.register(research_agent)

    orchestrator = SubAgentOrchestrator(registry=registry)

    task = TaskEnvelope(
        task_id="task-001",
        user_query="请调研 sub-agent 架构，比较官方文档、论文和开源实现，并给出代码框架建议。",
        subgoal="subagent-architecture-research",
        shared_context={"language": "zh-CN"},
    )

    result = await orchestrator.arun(task)

    print("=" * 88)
    print("ORCHESTRATION DECISION")
    print(result["decision"])
    print("=" * 88)
    print("MERGED RESULT")
    print(result["merged"])
    print("=" * 88)

    adapters = [
        OpenAIChatGPTAdapter(),
        ClaudeCodeAdapter(),
        DeepSeekAdapter(),
        GLMAdapter(),
        KimiAdapter(),
        MiniMaxAdapter(),
    ]

    rendered = {}
    for adapter in adapters:
        artifact = adapter.build_artifact(research_agent.definition, task.user_query)
        rendered[adapter.provider_name] = {
            "definition": artifact.definition,
            "invocation_example": artifact.invocation_example,
            "notes": artifact.notes,
        }

    out_path = Path(__file__).resolve().parent / "provider_artifacts.json"
    out_path.write_text(json.dumps(rendered, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Provider artifacts written to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
