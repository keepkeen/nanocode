from __future__ import annotations

from pathlib import Path

from nanocli.config import load_config


def test_load_config_merges_project_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
    global_config = tmp_path / "xdg_config" / "nanocli" / "config.toml"
    global_config.parent.mkdir(parents=True, exist_ok=True)
    global_config.write_text(
        """
default_profile = "claude"

[profiles.claude]
provider = "anthropic"
model = "claude-sonnet-4.6"
api_key_env = "ANTHROPIC_API_KEY"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    cwd = tmp_path / "repo"
    (cwd / ".nanocli").mkdir(parents=True, exist_ok=True)
    (cwd / ".nanocli" / "config.toml").write_text(
        """
default_profile = "openai"

[profiles.openai]
provider = "openai_responses"
model = "gpt-5.4"
api_key_env = "OPENAI_API_KEY"

[profiles.deepseek]
provider = "deepseek"
model = "deepseek-chat"
api_key_env = "DEEPSEEK_API_KEY"
base_url = "https://api.deepseek.com"

[mcp.servers.demo]
transport = "http"
url = "http://127.0.0.1:8876/"
protocol_version = "2025-11-25"
fallback_protocol_versions = ["2025-06-18"]
auth_mode = "bearer"
auth_token_env = "DEMO_MCP_TOKEN"
sampling_policy = "deny"
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    config = load_config(cwd)
    assert config.default_profile == "openai"
    assert config.profiles["openai"].provider == "openai_responses"
    assert config.profiles["claude"].provider == "anthropic"
    assert config.profiles["deepseek"].base_url == "https://api.deepseek.com"
    assert config.mcp_servers["demo"].protocol_version == "2025-11-25"
    assert config.mcp_servers["demo"].fallback_protocol_versions == ["2025-06-18"]
    assert config.mcp_servers["demo"].auth_token_env == "DEMO_MCP_TOKEN"
    assert config.mcp_servers["demo"].sampling_policy == "deny"
    assert config.mcp_servers["demo"].integration_mode == "auto"
    assert config.skills.auto_render_targets[2] == "claude-subagent"
    assert config.planning.skill == "repository_refactor"
    assert config.paths is not None
    assert config.paths.project_config == cwd / ".nanocli" / "config.toml"
