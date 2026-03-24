from __future__ import annotations

import json

from plan_todo_agent.planning.engine import DualLayerPlanTodoAgent
from plan_todo_agent.providers.openai_responses import OpenAIResponsesAdapter
from plan_todo_agent.skills.repository_refactor import RepositoryRefactorSkill


def main() -> None:
    skill = RepositoryRefactorSkill()
    provider = OpenAIResponsesAdapter(model="gpt-5", reasoning_effort="medium")
    agent = DualLayerPlanTodoAgent(provider=provider, skill=skill)

    state = agent.bootstrap(
        "Refactor the authentication module to introduce a token service abstraction while preserving backward compatibility."
    )

    request_payload = agent.build_provider_request(state)
    print("=== Provider Request Payload (OpenAI Responses) ===")
    print(json.dumps(request_payload, ensure_ascii=False, indent=2))

    print("\n=== Initial State ===")
    print(agent.summarize_state(state))

    state = agent.apply_execution_feedback(
        state,
        completed_step_ids=["S1"],
        observations=[
            "Auth entrypoints found in auth/service.py, auth/routes.py, and tests/test_auth.py.",
            "A legacy token helper is imported by two downstream modules.",
        ],
    )

    print("\n=== State After Completing S1 ===")
    print(agent.summarize_state(state))

    state = agent.apply_execution_feedback(
        state,
        completed_step_ids=["S2"],
        observations=[
            "Planned an adapter layer with a compatibility wrapper for legacy imports.",
            "Verification will use unit tests plus a smoke check for token refresh.",
        ],
    )

    print("\n=== State After Completing S2 ===")
    print(agent.summarize_state(state))


if __name__ == "__main__":
    main()
