from __future__ import annotations

import json

from nanocli.runtime import AgentRuntime


def test_runtime_dry_run_persists_memory_and_traces(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    (cwd / ".nanocli").mkdir(parents=True, exist_ok=True)
    (cwd / ".nanocli" / "config.toml").write_text(
        """
default_profile = "openai"

[profiles.openai]
provider = "openai_responses"
model = "gpt-5.4"
api_key_env = "OPENAI_API_KEY"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runtime = AgentRuntime(cwd=cwd)
    result = runtime.run("Implement a cache-safe planner", execute=False, debug=True)

    assert result.summary.status.value == "compiled"
    assert result.provider_request is not None
    assert any(trace.kind.value == "plan" for trace in result.traces)
    assert any(trace.kind.value == "provider_request" for trace in result.traces)
    snapshot_path = cwd / ".nanocli" / "project_memory.json"
    assert snapshot_path.exists()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["events"]
    assert snapshot["blocks"]

    second = AgentRuntime(cwd=cwd)
    project_snapshot = second.read_project_memory_snapshot()
    assert project_snapshot["namespace"].startswith("project:")
    assert len(project_snapshot["events"]) >= len(snapshot["events"])


def test_runtime_chat_turn_persists_session_skills_and_subagents(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    (cwd / ".nanocli").mkdir(parents=True, exist_ok=True)
    (cwd / ".nanocli" / "config.toml").write_text(
        """
default_profile = "openai"

[profiles.openai]
provider = "openai_responses"
model = "gpt-5.4"
api_key_env = "OPENAI_API_KEY"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    runtime = AgentRuntime(cwd=cwd)
    result = runtime.chat_turn(
        "Research and implement a planner runtime",
        execute=False,
        selected_skills=["travel-weather-briefing"],
        use_subagents=True,
    )

    assert result.session_id is not None
    assert result.provider_request is not None
    assert result.provider_request["diagnostics"]["skills"] == ["travel-weather-briefing"]
    assert result.subagent_summary is not None
    messages = runtime.get_session_messages(result.session_id)
    assert [message.role for message in messages] == ["user", "assistant"]
