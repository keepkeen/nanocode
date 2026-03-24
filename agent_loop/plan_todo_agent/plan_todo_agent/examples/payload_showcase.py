from __future__ import annotations

import json

from plan_todo_agent.planning.engine import DualLayerPlanTodoAgent
from plan_todo_agent.providers import (
    AnthropicAdapter,
    DeepSeekAdapter,
    GLMAdapter,
    KimiAdapter,
    MiniMaxAdapter,
    OpenAIResponsesAdapter,
)
from plan_todo_agent.renderers import ChatGPTRenderer, ClaudeCodeRenderer
from plan_todo_agent.skills import RepositoryRefactorSkill


def main() -> None:
    skill = RepositoryRefactorSkill()
    objective = "Plan and execute a safe multi-file refactor for the authentication stack."

    providers = {
        "openai": OpenAIResponsesAdapter(model="gpt-5"),
        "deepseek": DeepSeekAdapter(model="deepseek-chat", use_thinking_mode=True),
        "glm": GLMAdapter(model="glm-5", use_thinking_mode=True),
        "kimi": KimiAdapter(model="kimi-k2-0905-preview", use_thinking_mode=False),
        "anthropic": AnthropicAdapter(model="claude-sonnet-4-20250514", interleaved=True),
        "minimax": MiniMaxAdapter(model="MiniMax-M2.5"),
    }

    for name, provider in providers.items():
        agent = DualLayerPlanTodoAgent(provider=provider, skill=skill)
        state = agent.bootstrap(objective)
        payload = agent.build_provider_request(state)
        print(f"\n=== {name.upper()} ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    baseline_agent = DualLayerPlanTodoAgent(provider=OpenAIResponsesAdapter(), skill=skill)
    baseline_state = baseline_agent.bootstrap(objective)

    print("\n=== CLAUDE CODE settings.json example ===")
    print(
        ClaudeCodeRenderer.render_settings(
            {
                "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
                "ANTHROPIC_AUTH_TOKEN": "${MINIMAX_API_KEY}",
                "ANTHROPIC_MODEL": "MiniMax-M2.5",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            },
            default_mode="plan",
        )
    )

    print("\n=== CLAUDE CODE subagent example ===")
    print(
        ClaudeCodeRenderer.render_subagent(
            name="plan-executor",
            description="Use proactively for multi-file implementation planning, todo tracking, and verification-first execution.",
            tools=skill.build_tools(),
        )
    )

    print("\n=== CLAUDE.md example ===")
    print(ClaudeCodeRenderer.render_claude_md(baseline_state.plan))

    print("\n=== ChatGPT project/task/progress stubs ===")
    print(
        json.dumps(
            {
                "project": ChatGPTRenderer.render_project_stub(
                    name="Auth Refactor",
                    objective=objective,
                    files=["auth/service.py", "auth/routes.py", "tests/test_auth.py"],
                ),
                "task": ChatGPTRenderer.render_task_stub(
                    title="Review auth refactor status",
                    instructions="Check whether verification has finished and summarize blockers.",
                    schedule="Every weekday at 17:00",
                ),
                "progress": json.loads(
                    ChatGPTRenderer.render_progress_snapshot(baseline_state.plan, baseline_state.todos)
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
