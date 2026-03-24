from __future__ import annotations

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
