from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import os

from .models import ModelProfile, NanocliPaths, utc_now


def _mask_secret(value: str | None) -> str:
    if not value:
        return "-"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


@dataclass(slots=True)
class ApiKeyResolution:
    api_key_env: str
    value: str | None
    source: str
    source_path: Path | None = None
    updated_at: str | None = None

    @property
    def present(self) -> bool:
        return bool(self.value)

    @property
    def masked_value(self) -> str:
        return _mask_secret(self.value)

    def display_source(self) -> str:
        if self.source == "missing":
            return "missing"
        if self.source == "env":
            return f"env:{self.api_key_env}"
        if self.source_path is None:
            return self.source
        return f"{self.source}:{self.source_path}"


class AuthManager:
    def __init__(self, paths: NanocliPaths) -> None:
        self.paths = paths

    def resolve_api_key(self, profile: ModelProfile) -> ApiKeyResolution:
        env_value = os.getenv(profile.api_key_env)
        if env_value:
            return ApiKeyResolution(api_key_env=profile.api_key_env, value=env_value, source="env")

        for scope, path in (("project", self.paths.project_auth), ("global", self.paths.global_auth)):
            entry = self._read_store(path).get(profile.api_key_env)
            if entry and entry.get("value"):
                return ApiKeyResolution(
                    api_key_env=profile.api_key_env,
                    value=str(entry["value"]),
                    source=scope,
                    source_path=path,
                    updated_at=str(entry.get("updated_at") or ""),
                )
        return ApiKeyResolution(api_key_env=profile.api_key_env, value=None, source="missing")

    def list_profile_statuses(self, profiles: dict[str, ModelProfile]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for name, profile in profiles.items():
            resolution = self.resolve_api_key(profile)
            rows.append(
                {
                    "profile": name,
                    "provider": profile.provider,
                    "model": profile.model,
                    "api_key_env": profile.api_key_env,
                    "source": resolution.source,
                    "source_display": resolution.display_source(),
                    "masked_value": resolution.masked_value,
                    "present": resolution.present,
                    "updated_at": resolution.updated_at or "",
                }
            )
        return rows

    def set_api_key(self, api_key_env: str, value: str, *, scope: str = "global") -> dict[str, Any]:
        if not value.strip():
            raise ValueError("API key cannot be empty.")
        path = self._scope_path(scope)
        payload = self._read_store(path)
        payload[api_key_env] = {
            "value": value.strip(),
            "updated_at": utc_now().isoformat(),
        }
        self._write_store(path, payload)
        return {
            "api_key_env": api_key_env,
            "scope": scope,
            "path": str(path),
            "masked_value": _mask_secret(value.strip()),
        }

    def clear_api_key(self, api_key_env: str, *, scope: str = "global") -> dict[str, Any]:
        path = self._scope_path(scope)
        payload = self._read_store(path)
        existed = api_key_env in payload
        payload.pop(api_key_env, None)
        self._write_store(path, payload)
        return {
            "api_key_env": api_key_env,
            "scope": scope,
            "path": str(path),
            "removed": existed,
        }

    def _scope_path(self, scope: str) -> Path:
        normalized = scope.lower().strip()
        if normalized == "project":
            return self.paths.project_auth
        if normalized == "global":
            return self.paths.global_auth
        raise ValueError(f"Unsupported auth scope: {scope}")

    @staticmethod
    def _read_store(path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Invalid auth store: {path}") from exc
        return dict(payload.get("keys", {}))

    def _write_store(self, path: Path, payload: dict[str, dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"keys": payload}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
