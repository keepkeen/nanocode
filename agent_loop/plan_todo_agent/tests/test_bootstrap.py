from plan_todo_agent.planning.engine import DualLayerPlanTodoAgent
from plan_todo_agent.providers.openai_responses import OpenAIResponsesAdapter
from plan_todo_agent.skills.repository_refactor import RepositoryRefactorSkill


def test_bootstrap_creates_plan_and_todos() -> None:
    agent = DualLayerPlanTodoAgent(OpenAIResponsesAdapter(), RepositoryRefactorSkill())
    state = agent.bootstrap("Refactor auth module")
    assert state.plan.goal == "Refactor auth module"
    assert len(state.plan.steps) == 4
    assert len(state.todos) == 4
    assert any(todo.status.value == "in_progress" for todo in state.todos)
