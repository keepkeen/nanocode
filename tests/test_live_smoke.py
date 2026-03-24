from __future__ import annotations

import os

import pytest


LIVE_ENVS = {
    "openai_responses": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


@pytest.mark.skipif(
    not any(os.getenv(env_name) for env_name in LIVE_ENVS.values()),
    reason="live smoke tests require at least one provider API key",
)
def test_live_smoke_environment_is_configurable():
    configured = {provider: env_name for provider, env_name in LIVE_ENVS.items() if os.getenv(env_name)}
    assert configured
