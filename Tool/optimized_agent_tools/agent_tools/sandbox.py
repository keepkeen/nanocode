from __future__ import annotations

from pathlib import Path
import shutil

from .base import SandboxAdapter


class NoopSandboxAdapter(SandboxAdapter):
    name = "none"

    def wrap(self, argv: list[str], cwd: str, env: dict[str, str]) -> tuple[list[str], str, dict[str, str]]:
        return argv, cwd, env


class FirejailSandboxAdapter(SandboxAdapter):
    name = "firejail"

    def __init__(self, *, private_tmp: bool = True, net_none: bool = True) -> None:
        self.private_tmp = private_tmp
        self.net_none = net_none
        if shutil.which("firejail") is None:
            raise RuntimeError("firejail is not installed")

    def wrap(self, argv: list[str], cwd: str, env: dict[str, str]) -> tuple[list[str], str, dict[str, str]]:
        wrapped = ["firejail", "--quiet", "--whitelist=" + str(Path(cwd).resolve())]
        if self.private_tmp:
            wrapped.append("--private-tmp")
        if self.net_none:
            wrapped.append("--net=none")
        wrapped.extend(argv)
        return wrapped, cwd, env
