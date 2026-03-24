from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import tomllib

from .models import ChatOptions, ExperimentalOptions, LiveTestOptions, McpServerConfig, MemoryOptions, ModelProfile, NanocliConfig, PlanningOptions, SkillsOptions, SubagentOptions, ToolOptions, UIOptions
from .paths import resolve_paths


def _default_profiles() -> dict[str, ModelProfile]:
    return {
        "openai": ModelProfile(
            name="openai",
            provider="openai_responses",
            model="gpt-5.4",
            api_key_env="OPENAI_API_KEY",
            cache_mode="prompt_cache_key",
        ),
        "claude": ModelProfile(
            name="claude",
            provider="anthropic",
            model="claude-sonnet-4.6",
            api_key_env="ANTHROPIC_API_KEY",
            cache_mode="cache_control",
        ),
        "deepseek": ModelProfile(
            name="deepseek",
            provider="deepseek",
            model="deepseek-chat",
            api_key_env="DEEPSEEK_API_KEY",
            base_url="https://api.deepseek.com",
            tool_mode="auto",
        ),
        "glm": ModelProfile(
            name="glm",
            provider="glm",
            model="glm-5",
            api_key_env="ZAI_API_KEY",
            base_url="https://open.bigmodel.cn",
            tool_mode="auto",
        ),
        "kimi": ModelProfile(
            name="kimi",
            provider="kimi",
            model="kimi-k2.5",
            api_key_env="MOONSHOT_API_KEY",
            base_url="https://api.moonshot.cn/v1",
            tool_mode="auto",
        ),
        "minimax": ModelProfile(
            name="minimax",
            provider="minimax",
            model="MiniMax-M2.5",
            api_key_env="MINIMAX_API_KEY",
            base_url="https://api.minimaxi.com/v1",
            tool_mode="auto",
        ),
    }


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _coerce_profiles(raw_profiles: dict[str, Any]) -> dict[str, ModelProfile]:
    profiles = _default_profiles()
    for name, payload in raw_profiles.items():
        profiles[name] = ModelProfile(
            name=name,
            provider=str(payload["provider"]),
            model=str(payload["model"]),
            api_key_env=str(payload["api_key_env"]),
            base_url=payload.get("base_url"),
            max_tokens=int(payload.get("max_tokens", 4096)),
            tool_mode=str(payload.get("tool_mode", "auto")),
            cache_mode=str(payload.get("cache_mode", "auto")),
            extra={k: v for k, v in payload.items() if k not in {"provider", "model", "api_key_env", "base_url", "max_tokens", "tool_mode", "cache_mode"}},
        )
    return profiles


def _coerce_mcp_servers(raw: dict[str, Any]) -> dict[str, McpServerConfig]:
    servers: dict[str, McpServerConfig] = {}
    for name, payload in raw.items():
        servers[name] = McpServerConfig(
            name=name,
            transport=str(payload.get("transport", "http")),
            url=payload.get("url"),
            command=list(payload.get("command", [])),
            env={str(k): str(v) for k, v in payload.get("env", {}).items()},
            integration_mode=str(payload.get("integration_mode", payload.get("mode", "auto"))),
            startup_timeout_seconds=int(payload.get("startup_timeout_seconds", 15)),
            native_label=payload.get("native_label"),
            protocol_version=str(payload.get("protocol_version", "2025-11-25")),
            fallback_protocol_versions=[str(item) for item in payload.get("fallback_protocol_versions", ["2025-06-18"])],
            legacy_sse_fallback=bool(payload.get("legacy_sse_fallback", True)),
            headers={str(k): str(v) for k, v in payload.get("headers", {}).items()},
            auth_mode=str(payload.get("auth_mode", "none")),
            auth_token_env=payload.get("auth_token_env"),
            connect_timeout_seconds=int(payload.get("connect_timeout_seconds", payload.get("startup_timeout_seconds", 15))),
            request_timeout_seconds=int(payload.get("request_timeout_seconds", 60)),
            keepalive_seconds=int(payload.get("keepalive_seconds", 30)),
            max_inflight_requests=int(payload.get("max_inflight_requests", 16)),
            capabilities=dict(payload.get("capabilities", {})),
            sampling_policy=str(payload.get("sampling_policy", "ask")),
            elicitation_policy=str(payload.get("elicitation_policy", "ask")),
            roots_policy=str(payload.get("roots_policy", "workspace")),
            resume_streams=bool(payload.get("resume_streams", True)),
        )
    return servers


def load_config(cwd: Path | None = None, config_path: Path | None = None) -> NanocliConfig:
    root = (cwd or Path.cwd()).resolve()
    paths = resolve_paths(root)
    global_raw = _read_toml(paths.global_config)
    project_raw = _read_toml(paths.project_config)
    explicit_raw = _read_toml(config_path) if config_path else {}

    merged = _deep_merge(global_raw, project_raw)
    merged = _deep_merge(merged, explicit_raw)

    profiles = _coerce_profiles(merged.get("profiles", {}))
    default_profile = str(merged.get("default_profile", "openai"))
    if default_profile not in profiles:
        default_profile = "openai"

    config = NanocliConfig(
        default_profile=default_profile,
        profiles=profiles,
        chat=ChatOptions(**merged.get("chat", {})),
        memory=MemoryOptions(**merged.get("memory", {})),
        skills=SkillsOptions(**merged.get("skills", {})),
        tools=ToolOptions(**merged.get("tools", {})),
        planning=PlanningOptions(**merged.get("planning", {})),
        subagents=SubagentOptions(**merged.get("subagents", {})),
        ui=UIOptions(**merged.get("ui", {})),
        experimental=ExperimentalOptions(**merged.get("experimental", {})),
        live_tests=LiveTestOptions(**merged.get("testing", {}).get("live", {})),
        mcp_servers=_coerce_mcp_servers(merged.get("mcp", {}).get("servers", {})),
        system_policies=list(merged.get("system_policies", [])),
        user_instructions=list(merged.get("user_instructions", [])),
        paths=paths,
    )
    return config
