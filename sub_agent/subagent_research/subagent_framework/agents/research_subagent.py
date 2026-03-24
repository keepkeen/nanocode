from __future__ import annotations

import re
from typing import List

from ..abstractions import AbstractSubAgent
from ..models import ExecutionTrace, SubAgentDefinition, TaskEnvelope, TaskResult, ToolSpec, WorkingMemorySnapshot


class ResearchSubAgent(AbstractSubAgent):
    """A concrete sub-agent implementation.

    This agent is intentionally provider-neutral. In production you can replace the
    local analysis logic with real LLM calls while keeping the same definition.
    """

    def __init__(self) -> None:
        self.definition = SubAgentDefinition(
            name="research-analyst",
            description="Research specialist for document survey, latest papers, benchmarks, and implementation references. Use proactively for sub-agent architecture analysis.",
            system_prompt=(
                "You are a senior research sub-agent. Isolate the task, extract evidence, "
                "compress context by subgoal, and return a structured, implementation-ready answer."
            ),
            instructions=(
                "Focus on official documentation, recent papers, open-source projects, and "
                "actionable engineering implications. Prefer crisp sections over verbose prose."
            ),
            tags=["research", "survey", "paper", "benchmark", "sub-agent", "agent"],
            capabilities=[
                "official-doc-analysis",
                "multi-agent-literature-review",
                "benchmark-synthesis",
                "implementation-recommendation",
            ],
            model_preferences={
                "openai": "gpt-5",
                "openai_responses": "gpt-5",
                "claude_code": "sonnet",
                "deepseek": "deepseek-chat",
                "glm": "glm-5",
                "kimi": "kimi-k2.5",
                "minimax_openai": "MiniMax-M2.7",
                "minimax_anthropic": "MiniMax-M2.7",
            },
            tools=[
                ToolSpec(
                    name="web_search",
                    description="Search official documentation, papers, and repositories.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "top_k": {"type": "integer", "description": "Maximum result count", "default": 5},
                        },
                        "required": ["query"],
                    },
                ),
                ToolSpec(
                    name="emit_json_report",
                    description="Return a strict JSON report for downstream orchestration.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "body": {"type": "string"},
                        },
                        "required": ["title", "body"],
                    },
                ),
            ],
            constraints=[
                "Do not fabricate sources.",
                "Prefer hierarchical summaries when the task is long-horizon.",
                "Surface implementation trade-offs explicitly.",
            ],
            metadata={"version": "1.0.0", "owner": "demo"},
        )

    def can_handle(self, task: TaskEnvelope) -> bool:
        lowered = task.user_query.lower()
        keywords = ["research", "survey", "paper", "benchmark", "agent", "sub-agent", "架构", "调研", "论文"]
        return any(word in lowered for word in keywords) or not task.user_query.strip() == ""

    async def arun(self, task: TaskEnvelope, memory: WorkingMemorySnapshot) -> TaskResult:
        keywords = self._extract_keywords(task.user_query)
        memory_digest = " | ".join(entry.observation for entry in memory.active_entries[:3]) or "no prior focused memory"
        summary = (
            "Built a focused research brief with keyword extraction, architectural recommendations, "
            "and memory-aware context compression."
        )
        evidence = [
            f"keywords={', '.join(keywords[:8])}",
            f"active_subgoal={memory.active_subgoal or 'none'}",
            f"memory_digest={memory_digest}",
            "recommended pattern=hierarchical routing + provider-specific serialization",
        ]
        traces = [
            ExecutionTrace(
                phase="analyze",
                agent_name=self.definition.name,
                message="parsed task into research facets",
                payload={"keywords": keywords},
            ),
            ExecutionTrace(
                phase="compress",
                agent_name=self.definition.name,
                message="constructed compact context snapshot",
                payload={"memory_digest": memory_digest},
            ),
        ]
        structured_output = {
            "task": task.user_query,
            "keywords": keywords,
            "recommendations": [
                "use hierarchical working memory",
                "separate provider-independent sub-agent spec from provider adapters",
                "prefer parallel delegation only for orthogonal subtasks",
            ],
        }
        return TaskResult(
            success=True,
            agent_name=self.definition.name,
            summary=summary,
            structured_output=structured_output,
            evidence=evidence,
            traces=traces,
        )

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        return re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", text.lower())
