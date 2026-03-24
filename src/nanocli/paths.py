from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

from .models import NanocliPaths


def resolve_paths(cwd: Path) -> NanocliPaths:
    global_config_dir = Path(user_config_dir("nanocli"))
    data_dir = Path(user_data_dir("nanocli"))
    project_dir = cwd / ".nanocli"
    artifacts_dir = data_dir / "artifacts"
    return NanocliPaths(
        global_config=global_config_dir / "config.toml",
        project_config=project_dir / "config.toml",
        global_auth=global_config_dir / "auth.json",
        project_auth=project_dir / "auth.json",
        data_dir=data_dir,
        project_dir=project_dir,
        db_path=data_dir / "state.db",
        artifacts_dir=artifacts_dir,
    )
