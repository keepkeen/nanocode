from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import re

from .types import Decision, RiskLevel, ToolName
from .utils import extract_domain, is_private_host, is_within_roots, matches_any, normalize_url, parse_command


@dataclass(slots=True)
class PolicyDecision:
    decision: Decision
    risk: RiskLevel
    reasons: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW


@dataclass(slots=True)
class CommandRule:
    pattern: str
    decision: Decision
    risk: RiskLevel
    reason: str


@dataclass(slots=True)
class UrlRule:
    pattern: str
    decision: Decision
    risk: RiskLevel
    reason: str


DEFAULT_COMMAND_RULES: list[CommandRule] = [
    CommandRule(r"(^|\s)sudo(\s|$)", Decision.DENY, RiskLevel.CRITICAL, "sudo is not allowed"),
    CommandRule(r"(^|\s)(su|doas)(\s|$)", Decision.DENY, RiskLevel.CRITICAL, "privilege escalation is not allowed"),
    CommandRule(r"(^|\s)rm\s+-rf\s+/(\s|$)", Decision.DENY, RiskLevel.CRITICAL, "destructive filesystem wipe is blocked"),
    CommandRule(r"(^|\s)(mkfs|fdisk|parted|dd)(\s|$)", Decision.DENY, RiskLevel.CRITICAL, "disk-level mutation is blocked"),
    CommandRule(r"(^|\s)(shutdown|reboot|halt|poweroff)(\s|$)", Decision.DENY, RiskLevel.CRITICAL, "system power commands are blocked"),
    CommandRule(r"(^|\s)(iptables|ufw|sysctl)(\s|$)", Decision.DENY, RiskLevel.CRITICAL, "host network/kernel mutation is blocked"),
    CommandRule(r"(^|\s)docker\s+run\b.*--privileged", Decision.DENY, RiskLevel.CRITICAL, "privileged containers are blocked"),
    CommandRule(r"curl\b.*\|\s*(sh|bash)\b", Decision.DENY, RiskLevel.CRITICAL, "pipe-to-shell is blocked"),
    CommandRule(r"wget\b.*\|\s*(sh|bash)\b", Decision.DENY, RiskLevel.CRITICAL, "pipe-to-shell is blocked"),
    CommandRule(r"(^|\s)(nc|ncat|netcat|telnet|ssh|scp|sftp)(\s|$)", Decision.ASK, RiskLevel.HIGH, "outbound interactive/network commands require approval"),
    CommandRule(r"(^|\s)(git\s+push|gh\s+pr\s+create|gh\s+release)(\s|$)", Decision.ASK, RiskLevel.HIGH, "remote write actions require approval"),
    CommandRule(r"(^|\s)(pip|npm|pnpm|yarn|cargo|go)\s+(publish|login)\b", Decision.ASK, RiskLevel.HIGH, "package publishing or auth changes require approval"),
    CommandRule(r"(^|\s)(chmod|chown)\b", Decision.ASK, RiskLevel.MEDIUM, "permission changes require approval"),
]


DEFAULT_URL_RULES: list[UrlRule] = [
    UrlRule("*.localhost", Decision.DENY, RiskLevel.CRITICAL, "localhost is blocked"),
    UrlRule("localhost", Decision.DENY, RiskLevel.CRITICAL, "localhost is blocked"),
    UrlRule("169.254.*", Decision.DENY, RiskLevel.CRITICAL, "link-local metadata ranges are blocked"),
    UrlRule("127.*", Decision.DENY, RiskLevel.CRITICAL, "loopback ranges are blocked"),
    UrlRule("10.*", Decision.DENY, RiskLevel.CRITICAL, "private network ranges are blocked"),
    UrlRule("192.168.*", Decision.DENY, RiskLevel.CRITICAL, "private network ranges are blocked"),
    UrlRule("172.16.*", Decision.DENY, RiskLevel.CRITICAL, "private network ranges are blocked"),
]


class SecurityPolicy:
    def __init__(
        self,
        *,
        workspace_root: str | Path,
        read_roots: Iterable[str | Path] | None = None,
        write_roots: Iterable[str | Path] | None = None,
        env_allowlist: Iterable[str] | None = None,
        command_rules: list[CommandRule] | None = None,
        url_rules: list[UrlRule] | None = None,
        allow_private_network: bool = False,
        allow_shell_compounds: bool = False,
        max_command_runtime_sec: int = 30,
        max_command_output_bytes: int = 256_000,
        max_http_response_bytes: int = 1_000_000,
        max_redirects: int = 4,
        require_url_provenance: bool = True,
        allow_http_upgrade: bool = True,
        webfetch_allowed_domains: Iterable[str] | None = None,
        webfetch_blocked_domains: Iterable[str] | None = None,
        websearch_allowed_domains: Iterable[str] | None = None,
        websearch_blocked_domains: Iterable[str] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.read_roots = [Path(p).resolve() for p in (read_roots or [self.workspace_root])]
        self.write_roots = [Path(p).resolve() for p in (write_roots or [self.workspace_root])]
        self.env_allowlist = set(env_allowlist or ["PATH", "HOME", "LANG", "LC_ALL", "TERM", "TMPDIR"])
        self.command_rules = command_rules or list(DEFAULT_COMMAND_RULES)
        self.url_rules = url_rules or list(DEFAULT_URL_RULES)
        self.allow_private_network = allow_private_network
        self.allow_shell_compounds = allow_shell_compounds
        self.max_command_runtime_sec = max_command_runtime_sec
        self.max_command_output_bytes = max_command_output_bytes
        self.max_http_response_bytes = max_http_response_bytes
        self.max_redirects = max_redirects
        self.require_url_provenance = require_url_provenance
        self.allow_http_upgrade = allow_http_upgrade
        self.webfetch_allowed_domains = list(webfetch_allowed_domains or [])
        self.webfetch_blocked_domains = list(webfetch_blocked_domains or [])
        self.websearch_allowed_domains = list(websearch_allowed_domains or [])
        self.websearch_blocked_domains = list(websearch_blocked_domains or [])

    def sanitize_env(self, env: dict[str, str]) -> dict[str, str]:
        return {k: v for k, v in env.items() if k in self.env_allowlist}

    def validate_cwd(self, cwd: str | Path) -> PolicyDecision:
        path = Path(cwd).resolve()
        if is_within_roots(path, self.read_roots):
            return PolicyDecision(Decision.ALLOW, RiskLevel.LOW, [f"cwd within allowed roots: {path}"])
        return PolicyDecision(Decision.DENY, RiskLevel.HIGH, [f"cwd outside allowed roots: {path}"])

    def can_write_path(self, path: str | Path) -> bool:
        return is_within_roots(Path(path).resolve(), self.write_roots)

    def decide_tool(self, tool_name: ToolName) -> PolicyDecision:
        if tool_name in {ToolName.WEBSEARCH, ToolName.WEBFETCH, ToolName.BASH}:
            return PolicyDecision(Decision.ALLOW, RiskLevel.LOW, [f"tool {tool_name.value} enabled"])
        return PolicyDecision(Decision.DENY, RiskLevel.HIGH, [f"tool {tool_name.value} not enabled"])

    def decide_bash(self, command: str, *, cwd: str | Path) -> PolicyDecision:
        reasons: list[str] = []
        cwd_decision = self.validate_cwd(cwd)
        if cwd_decision.decision == Decision.DENY:
            return cwd_decision

        parsed = parse_command(command)
        if not parsed.tokens:
            return PolicyDecision(Decision.DENY, RiskLevel.MEDIUM, ["empty command is not allowed"])

        for rule in self.command_rules:
            if re.search(rule.pattern, command, flags=re.IGNORECASE):
                reasons.append(rule.reason)
                return PolicyDecision(rule.decision, rule.risk, reasons)

        if parsed.contains_shell_metacharacters and not self.allow_shell_compounds:
            reasons.append("compound shell syntax requires approval")
            return PolicyDecision(Decision.ASK, RiskLevel.MEDIUM, reasons)

        risk = RiskLevel.LOW
        decision = Decision.ALLOW
        first = parsed.tokens[0]
        if first in {"python", "python3", "node", "ruby", "perl", "php"}:
            reasons.append("interpreter execution may run arbitrary code")
            risk = RiskLevel.MEDIUM
        if first in {"git", "gh"}:
            reasons.append("vcs command may affect repository state")
            risk = max(risk, RiskLevel.MEDIUM, key=lambda x: [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL].index(x))
        if any(tok.startswith("/") and not self.can_write_path(tok) for tok in parsed.tokens if any(ch.isalpha() for ch in tok)):
            reasons.append("command references absolute path outside write roots")
            decision = Decision.ASK
            risk = RiskLevel.MEDIUM
        if command.count("&&") + command.count("||") >= 2:
            reasons.append("long chained command requires approval")
            decision = Decision.ASK
            risk = RiskLevel.MEDIUM
        if not reasons:
            reasons.append("command allowed by default policy")
        return PolicyDecision(decision, risk, reasons)

    def _apply_domain_lists(self, domain: str, *, allowed: list[str], blocked: list[str]) -> PolicyDecision | None:
        if blocked and matches_any(domain, blocked):
            return PolicyDecision(Decision.DENY, RiskLevel.HIGH, [f"domain blocked by policy: {domain}"])
        if allowed and not matches_any(domain, allowed):
            return PolicyDecision(Decision.DENY, RiskLevel.HIGH, [f"domain not in allowlist: {domain}"])
        return None

    def decide_url(self, url: str, *, tool: ToolName) -> tuple[str | None, PolicyDecision]:
        reasons: list[str] = []
        try:
            normalized = normalize_url(url, upgrade_insecure=self.allow_http_upgrade)
        except Exception as exc:
            return None, PolicyDecision(Decision.DENY, RiskLevel.HIGH, [f"invalid URL: {exc}"])

        domain = extract_domain(normalized)
        if not domain:
            return None, PolicyDecision(Decision.DENY, RiskLevel.HIGH, ["URL has no hostname"])

        private_host = is_private_host(domain)
        if not self.allow_private_network and private_host:
            return normalized, PolicyDecision(Decision.DENY, RiskLevel.CRITICAL, [f"private or local host blocked: {domain}"])

        for rule in self.url_rules:
            if private_host and self.allow_private_network:
                continue
            if matches_any(domain, [rule.pattern]):
                return normalized, PolicyDecision(rule.decision, rule.risk, [rule.reason])

        if tool == ToolName.WEBFETCH:
            domain_decision = self._apply_domain_lists(domain, allowed=self.webfetch_allowed_domains, blocked=self.webfetch_blocked_domains)
        else:
            domain_decision = self._apply_domain_lists(domain, allowed=self.websearch_allowed_domains, blocked=self.websearch_blocked_domains)
        if domain_decision is not None:
            return normalized, domain_decision

        if normalized.startswith("http://"):
            reasons.append("insecure HTTP was retained")
            return normalized, PolicyDecision(Decision.ASK, RiskLevel.MEDIUM, reasons)

        reasons.append(f"URL allowed for {tool.value}: {domain}")
        return normalized, PolicyDecision(Decision.ALLOW, RiskLevel.LOW, reasons)
