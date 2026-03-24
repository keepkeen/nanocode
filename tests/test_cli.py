from __future__ import annotations

import json

from typer.testing import CliRunner

from nanocli.cli import app
from nanocli.runtime import AgentRuntime


def _write_basic_config(cwd):
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


def test_cli_run_no_execute(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    monkeypatch.chdir(cwd)

    runner = CliRunner()
    result = runner.invoke(app, ["run", "Draft a plan", "--no-execute"])
    assert result.exit_code == 0, result.stdout
    assert "compiled" in result.stdout.lower()


def test_cli_chat_start_one_shot_and_skills_render(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    monkeypatch.chdir(cwd)

    runner = CliRunner()
    chat = runner.invoke(app, ["chat", "start", "Research the planner", "--no-execute", "--one-shot", "--skill", "travel-weather-briefing", "--subagents"])
    render = runner.invoke(app, ["skills", "render", "--name", "travel-weather-briefing", "--target", "chatgpt"])

    assert chat.exit_code == 0, chat.stdout
    assert "session" in chat.stdout.lower()
    assert render.exit_code == 0, render.stdout
    assert (cwd / ".nanocli" / "generated" / "chatgpt" / "travel-weather-briefing" / "SKILL.md").exists()


def test_cli_root_print_and_continue_reuses_session(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    monkeypatch.chdir(cwd)

    runner = CliRunner()
    first = runner.invoke(app, ["--no-execute", "--print", "Research", "the", "planner"])
    second = runner.invoke(app, ["--continue", "--no-execute", "--print", "Follow", "up"])

    assert first.exit_code == 0, first.stdout
    assert second.exit_code == 0, second.stdout

    runtime = AgentRuntime(cwd)
    sessions = runtime.list_sessions(limit=10)
    assert len(sessions) == 1
    messages = runtime.get_session_messages(sessions[0].session_id)
    assert len([message for message in messages if message.role == "assistant"]) >= 2


def test_cli_root_starts_repl_and_supports_clear(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    monkeypatch.chdir(cwd)

    runner = CliRunner()
    result = runner.invoke(app, ["--no-execute"], input="/status\n/clear\n/quit\n")

    assert result.exit_code == 0, result.stdout
    assert "nanocode status" in result.stdout.lower()

    runtime = AgentRuntime(cwd)
    assert len(runtime.list_sessions(limit=10)) == 2


def test_cli_repl_supports_models_apikey_and_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    monkeypatch.chdir(cwd)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["--no-execute"],
        input="/models\n/apikey set openai sk-test-12345678\n/activity off\n/status\n/quit\n",
    )

    assert result.exit_code == 0, result.stdout
    assert "profiles" in result.stdout.lower()
    assert "stored OPENAI_API_KEY".lower() in result.stdout.lower()
    assert "activity" in result.stdout.lower()

    runtime = AgentRuntime(cwd)
    auth_payload = json.loads(runtime.paths.global_auth.read_text(encoding="utf-8"))
    assert auth_payload["keys"]["OPENAI_API_KEY"]["value"] == "sk-test-12345678"


def test_cli_print_mode_displays_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    monkeypatch.chdir(cwd)

    runner = CliRunner()
    result = runner.invoke(app, ["--no-execute", "--print", "Research", "the", "planner"])

    assert result.exit_code == 0, result.stdout
    assert "activity" in result.stdout.lower()
    assert "planner state persisted" in result.stdout.lower()


def test_runtime_resolves_stored_api_key_for_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    cwd = tmp_path / "repo"
    _write_basic_config(cwd)
    monkeypatch.chdir(cwd)

    runtime = AgentRuntime(cwd)
    runtime.set_api_key("openai", "sk-runtime-12345678", scope="project")

    captured: dict[str, str] = {}

    def fake_invoke(request, profile, api_key):
        captured["api_key"] = api_key
        return {"output_text": "Stored auth works."}

    monkeypatch.setattr(runtime, "_invoke_provider", fake_invoke)
    result = runtime.run("Test stored API key resolution", execute=True)

    assert result.summary.status.value == "completed"
    assert captured["api_key"] == "sk-runtime-12345678"
