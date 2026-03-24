from __future__ import annotations

from typer.testing import CliRunner

from nanocli.cli import app


def test_cli_run_no_execute(tmp_path, monkeypatch):
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
    monkeypatch.chdir(cwd)

    runner = CliRunner()
    result = runner.invoke(app, ["run", "Draft a plan", "--no-execute"])
    assert result.exit_code == 0, result.stdout
    assert "compiled" in result.stdout.lower()


def test_cli_chat_start_one_shot_and_skills_render(tmp_path, monkeypatch):
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
    monkeypatch.chdir(cwd)

    runner = CliRunner()
    chat = runner.invoke(app, ["chat", "start", "Research the planner", "--no-execute", "--one-shot", "--skill", "travel-weather-briefing", "--subagents"])
    render = runner.invoke(app, ["skills", "render", "--name", "travel-weather-briefing", "--target", "chatgpt"])

    assert chat.exit_code == 0, chat.stdout
    assert "session" in chat.stdout.lower()
    assert render.exit_code == 0, render.stdout
    assert (cwd / ".nanocli" / "generated" / "chatgpt" / "travel-weather-briefing" / "SKILL.md").exists()
