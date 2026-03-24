from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from subprocess import Popen, PIPE
from typing import Any
import os
import selectors
import signal
import time

from .audit import AuditLogger
from .base import AgentTool
from .policy import PolicyDecision, SecurityPolicy
from .sandbox import NoopSandboxAdapter
from .types import CommandExecution, CommandResult, Decision, RiskLevel, ToolContext, ToolName, ToolResult, WarningItem
from .utils import parse_command


class SecureBashTool(AgentTool):
    name = ToolName.BASH.value

    def __init__(self, *, policy: SecurityPolicy, audit: AuditLogger | None = None, sandbox=None) -> None:
        self.policy = policy
        self.audit = audit
        self.sandbox = sandbox or NoopSandboxAdapter()

    def plan(self, command: str, *, cwd: str | Path, env: dict[str, str] | None = None) -> tuple[PolicyDecision, CommandExecution]:
        decision = self.policy.decide_bash(command, cwd=cwd)
        parsed = parse_command(command)
        sanitized_env = self.policy.sanitize_env(env or dict(os.environ))
        execution = CommandExecution(
            argv=parsed.tokens,
            shell=parsed.contains_shell_metacharacters,
            cwd=str(Path(cwd).resolve()),
            timeout_sec=self.policy.max_command_runtime_sec,
            env=sanitized_env,
            requires_approval=decision.decision == Decision.ASK,
            risk=decision.risk,
            reasons=list(decision.reasons),
        )
        return decision, execution

    def _run_process(self, execution: CommandExecution, original_command: str) -> CommandResult:
        started = time.monotonic()
        argv = execution.argv
        cwd = execution.cwd
        env = execution.env
        shell = execution.shell
        if shell:
            argv = ["/bin/bash", "-lc", original_command]
        wrapped_argv, wrapped_cwd, wrapped_env = self.sandbox.wrap(argv, cwd, env)
        process = Popen(
            wrapped_argv,
            cwd=wrapped_cwd,
            env=wrapped_env,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
            text=False,
            bufsize=0,
            start_new_session=True,
        )
        if process.stdin:
            process.stdin.close()

        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        total = 0
        truncated = False
        timed_out = False

        sel = selectors.DefaultSelector()
        if process.stdout is not None:
            sel.register(process.stdout, selectors.EVENT_READ, data="stdout")
        if process.stderr is not None:
            sel.register(process.stderr, selectors.EVENT_READ, data="stderr")

        try:
            while sel.get_map():
                if time.monotonic() - started > execution.timeout_sec:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGKILL)
                    break
                events = sel.select(timeout=0.1)
                if not events and process.poll() is not None:
                    break
                for key, _ in events:
                    chunk = key.fileobj.read1(8192) if hasattr(key.fileobj, "read1") else key.fileobj.read(8192)
                    if not chunk:
                        sel.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if total > self.policy.max_command_output_bytes:
                        keep = max(0, len(chunk) - (total - self.policy.max_command_output_bytes))
                        chunk = chunk[:keep]
                        truncated = True
                    if key.data == "stdout":
                        stdout_chunks.append(chunk)
                    else:
                        stderr_chunks.append(chunk)
                    if truncated:
                        os.killpg(process.pid, signal.SIGKILL)
                        break
                if truncated:
                    break
            process.wait(timeout=1)
        except Exception:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except Exception:
                pass
            raise
        finally:
            try:
                sel.close()
            except Exception:
                pass
            for fh in (process.stdout, process.stderr):
                try:
                    if fh is not None:
                        fh.close()
                except Exception:
                    pass

        duration_ms = int((time.monotonic() - started) * 1000)
        return CommandResult(
            command=original_command,
            exit_code=process.returncode if process.returncode is not None else -9,
            stdout=b"".join(stdout_chunks).decode("utf-8", errors="replace"),
            stderr=b"".join(stderr_chunks).decode("utf-8", errors="replace"),
            timed_out=timed_out,
            truncated=truncated,
            duration_ms=duration_ms,
            metadata={
                "cwd": cwd,
                "sandbox": getattr(self.sandbox, "name", "none"),
            },
        )

    def invoke(
        self,
        ctx: ToolContext,
        **kwargs: Any,
    ) -> ToolResult:
        command = str(kwargs.get("command", ""))
        cwd = kwargs.get("cwd", ctx.cwd)
        env = kwargs.get("env")
        allow_ask = bool(kwargs.get("allow_ask", False))

        decision, execution = self.plan(command, cwd=cwd, env=env)
        warnings: list[WarningItem] = []
        if decision.decision == Decision.DENY:
            result = ToolResult(
                ok=False,
                tool=ToolName.BASH,
                summary="command denied by policy",
                data={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "decision": decision.decision.value,
                    "execution": asdict(execution),
                },
                warnings=[WarningItem(code="bash_denied", message="; ".join(decision.reasons), risk=decision.risk)],
            )
            self._audit(ctx, decision, {"command": command, "cwd": str(cwd)}, result)
            return result
        if decision.decision == Decision.ASK and not allow_ask:
            result = ToolResult(
                ok=False,
                tool=ToolName.BASH,
                summary="command requires approval",
                data={
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "decision": decision.decision.value,
                    "execution": asdict(execution),
                },
                warnings=[WarningItem(code="bash_approval_required", message="; ".join(decision.reasons), risk=decision.risk)],
            )
            self._audit(ctx, decision, {"command": command, "cwd": str(cwd)}, result)
            return result

        if execution.shell and not execution.argv:
            result = ToolResult(
                ok=False,
                tool=ToolName.BASH,
                summary="command parse failed",
                data={"timestamp": datetime.now(timezone.utc).isoformat()},
                warnings=[WarningItem(code="bash_parse_error", message="no executable tokens found", risk=RiskLevel.MEDIUM)],
            )
            self._audit(ctx, PolicyDecision(Decision.DENY, RiskLevel.MEDIUM, ["parse failed"]), {"command": command}, result)
            return result

        run = self._run_process(execution, command)
        if run.timed_out:
            warnings.append(WarningItem(code="bash_timed_out", message="command exceeded timeout", risk=RiskLevel.HIGH))
        if run.truncated:
            warnings.append(WarningItem(code="bash_output_truncated", message="output exceeded byte budget", risk=RiskLevel.MEDIUM))

        ok = run.exit_code == 0 and not run.timed_out
        summary = "command completed" if ok else "command finished with issues"
        result = ToolResult(
            ok=ok,
            tool=ToolName.BASH,
            summary=summary,
            data={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "decision": Decision.ALLOW.value if decision.decision == Decision.ALLOW else Decision.ASK.value,
                "execution": asdict(execution),
                "run": asdict(run),
            },
            warnings=warnings,
        )
        self._audit(ctx, decision, {"command": command, "cwd": str(cwd)}, result)
        return result

    def _audit(self, ctx: ToolContext, decision: PolicyDecision, payload: dict[str, Any], result: ToolResult) -> None:
        if not self.audit:
            return
        record = self.audit.write(
            session_id=ctx.session_id,
            tool=self.name,
            decision=decision.decision.value,
            payload=payload,
            result=result,
            notes=list(decision.reasons),
        )
        result.audit_id = record.audit_id
