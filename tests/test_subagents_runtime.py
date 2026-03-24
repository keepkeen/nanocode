from __future__ import annotations

from nanocli.subagents_runtime import SubagentManager


def test_subagent_manager_runs_parallel_mesh():
    manager = SubagentManager(max_parallel_agents=3, timeout_seconds=5)
    payload = manager.run(
        task_id="run-1",
        query="Research and review an implementation plan for the agent runtime",
        shared_context={"cwd": "/tmp/example"},
    )
    summary = manager.summarize("run-1", payload)

    assert payload["decision"]["selected_agents"]
    assert "Task:" in payload["merged"]
    assert summary.selected_agents
    assert summary.run_id == "run-1"
