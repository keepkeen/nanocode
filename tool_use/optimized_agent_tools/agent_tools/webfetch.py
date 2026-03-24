from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
import ssl

from .audit import AuditLogger
from .base import AgentTool
from .content_pipeline import BudgetConfig, extract_and_rank
from .policy import PolicyDecision, SecurityPolicy
from .types import Decision, FetchContent, RiskLevel, ToolContext, ToolName, ToolResult, WarningItem
from .utils import extract_title


class _PolicyRedirectHandler(request.HTTPRedirectHandler):
    def __init__(self, policy: SecurityPolicy) -> None:
        super().__init__()
        self.policy = policy
        self.redirects: list[str] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        normalized, decision = self.policy.decide_url(newurl, tool=ToolName.WEBFETCH)
        if decision.decision == Decision.DENY:
            raise URLError("redirect target blocked by policy")
        if normalized:
            self.redirects.append(normalized)
        return super().redirect_request(req, fp, code, msg, headers, normalized or newurl)


class SecureWebFetchTool(AgentTool):
    name = ToolName.WEBFETCH.value

    def __init__(
        self,
        *,
        policy: SecurityPolicy,
        audit: AuditLogger | None = None,
        user_agent: str = "optimized-agent-tools/0.2",
        budget: BudgetConfig | None = None,
    ) -> None:
        self.policy = policy
        self.audit = audit
        self.user_agent = user_agent
        self.budget = budget or BudgetConfig()

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

    def invoke(self, ctx: ToolContext, **kwargs: Any) -> ToolResult:
        session_state = kwargs.get("session_state")
        url = str(kwargs.get("url", ""))
        query = str(kwargs.get("query", "") or "")
        user_supplied = bool(kwargs.get("user_supplied", False))
        allow_ask = bool(kwargs.get("allow_ask", False))

        normalized, decision = self.policy.decide_url(url, tool=ToolName.WEBFETCH)
        payload = {"url": url, "normalized_url": normalized, "query": query}
        if decision.decision == Decision.DENY or not normalized:
            result = ToolResult(
                ok=False,
                tool=ToolName.WEBFETCH,
                summary="URL denied by policy",
                data={"timestamp": datetime.now(timezone.utc).isoformat(), "decision": decision.decision.value, "url": normalized or url},
                warnings=[WarningItem(code="webfetch_denied", message="; ".join(decision.reasons), risk=decision.risk)],
            )
            self._audit(ctx, decision, payload, result)
            return result
        if decision.decision == Decision.ASK and not allow_ask:
            result = ToolResult(
                ok=False,
                tool=ToolName.WEBFETCH,
                summary="URL requires approval",
                data={"timestamp": datetime.now(timezone.utc).isoformat(), "decision": decision.decision.value, "url": normalized},
                warnings=[WarningItem(code="webfetch_requires_approval", message="; ".join(decision.reasons), risk=decision.risk)],
            )
            self._audit(ctx, decision, payload, result)
            return result

        if session_state is not None and self.policy.require_url_provenance:
            if user_supplied:
                session_state.remember_urls([normalized])
            elif not session_state.is_url_known(normalized):
                denial = PolicyDecision(Decision.DENY, RiskLevel.HIGH, ["URL provenance check failed; only user-supplied or previously discovered URLs may be fetched"])
                result = ToolResult(
                    ok=False,
                    tool=ToolName.WEBFETCH,
                    summary="URL provenance check failed",
                    data={"timestamp": datetime.now(timezone.utc).isoformat(), "decision": denial.decision.value, "url": normalized},
                    warnings=[WarningItem(code="webfetch_unknown_url", message=denial.reasons[0], risk=denial.risk)],
                )
                self._audit(ctx, denial, payload, result)
                return result

        redirect_handler = _PolicyRedirectHandler(self.policy)
        ssl_ctx = ssl.create_default_context()
        opener = request.build_opener(request.HTTPSHandler(context=ssl_ctx), redirect_handler)
        opener.addheaders = [("User-Agent", self.user_agent)]

        warnings: list[WarningItem] = []
        try:
            req = request.Request(normalized, method="GET")
            with opener.open(req, timeout=15) as resp:
                content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                status = getattr(resp, "status", 200)
                chunks: list[bytes] = []
                total = 0
                truncated = False
                while True:
                    chunk = resp.read(16384)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.policy.max_http_response_bytes:
                        keep = max(0, len(chunk) - (total - self.policy.max_http_response_bytes))
                        chunk = chunk[:keep]
                        truncated = True
                    chunks.append(chunk)
                    if truncated:
                        break
                final_url = getattr(resp, "geturl", lambda: normalized)()
        except HTTPError as exc:
            result = ToolResult(
                ok=False,
                tool=ToolName.WEBFETCH,
                summary=f"HTTP error: {exc.code}",
                data={"timestamp": datetime.now(timezone.utc).isoformat(), "status_code": exc.code, "url": normalized},
                warnings=[WarningItem(code="webfetch_http_error", message=str(exc), risk=RiskLevel.MEDIUM)],
            )
            self._audit(ctx, PolicyDecision(Decision.ALLOW, RiskLevel.LOW, ["request attempted"]), payload, result)
            return result
        except URLError as exc:
            result = ToolResult(
                ok=False,
                tool=ToolName.WEBFETCH,
                summary="network error during fetch",
                data={"timestamp": datetime.now(timezone.utc).isoformat(), "url": normalized},
                warnings=[WarningItem(code="webfetch_network_error", message=str(exc.reason), risk=RiskLevel.MEDIUM)],
            )
            self._audit(ctx, PolicyDecision(Decision.ALLOW, RiskLevel.LOW, ["request attempted"]), payload, result)
            return result

        if len(redirect_handler.redirects) > self.policy.max_redirects:
            result = ToolResult(
                ok=False,
                tool=ToolName.WEBFETCH,
                summary="too many redirects",
                data={"timestamp": datetime.now(timezone.utc).isoformat(), "url": normalized, "redirects": redirect_handler.redirects},
                warnings=[WarningItem(code="webfetch_redirects", message="redirect count exceeded policy", risk=RiskLevel.MEDIUM)],
            )
            self._audit(ctx, PolicyDecision(Decision.DENY, RiskLevel.MEDIUM, ["too many redirects"]), payload, result)
            return result

        final_normalized, final_decision = self.policy.decide_url(final_url, tool=ToolName.WEBFETCH)
        if final_decision.decision == Decision.DENY or not final_normalized:
            result = ToolResult(
                ok=False,
                tool=ToolName.WEBFETCH,
                summary="final redirect target denied",
                data={"timestamp": datetime.now(timezone.utc).isoformat(), "url": final_url},
                warnings=[WarningItem(code="webfetch_final_url_denied", message="; ".join(final_decision.reasons), risk=final_decision.risk)],
            )
            self._audit(ctx, final_decision, payload, result)
            return result

        raw = b"".join(chunks)
        if truncated:
            warnings.append(WarningItem(code="webfetch_truncated", message="response exceeded byte budget", risk=RiskLevel.MEDIUM))
        if content_type and not any(content_type.startswith(prefix) for prefix in ("text/", "application/json", "application/xml", "application/xhtml+xml")):
            warnings.append(WarningItem(code="webfetch_non_text", message=f"fetched content-type is {content_type}", risk=RiskLevel.LOW))

        decoded = raw.decode("utf-8", errors="replace")
        title = extract_title(decoded)
        is_html = "html" in content_type or "xml" in content_type or "<html" in decoded.lower()
        summary, evidence_chunks, extraction_stats = extract_and_rank(decoded, query, is_html=is_html, budget=self.budget)
        content = FetchContent(
            url=normalized,
            final_url=final_normalized,
            title=title,
            text=summary,
            content_type=content_type or "text/plain",
            status_code=status,
            redirects=list(redirect_handler.redirects),
            metadata={
                "raw_length": len(raw),
                "hostname": urlparse(final_normalized).hostname or "",
                "evidence_chunk_count": len(evidence_chunks),
            },
        )
        if session_state is not None:
            session_state.remember_urls([normalized, final_normalized])

        result = ToolResult(
            ok=True,
            tool=ToolName.WEBFETCH,
            summary="web page fetched and compressed",
            data={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "content": {
                    "url": content.url,
                    "final_url": content.final_url,
                    "title": content.title,
                    "summary": summary,
                    "text": summary,
                    "evidence_chunks": [
                        {"text": item.text, "score": round(item.score, 4), "query_hits": item.query_hits, "start": item.start, "end": item.end}
                        for item in evidence_chunks
                    ],
                    "content_type": content.content_type,
                    "status_code": content.status_code,
                    "redirects": content.redirects,
                    "metadata": content.metadata,
                },
                "filtering": {
                    "raw_chars": extraction_stats.raw_chars,
                    "visible_chars": extraction_stats.visible_chars,
                    "dropped_boilerplate_blocks": extraction_stats.dropped_boilerplate_blocks,
                    "dropped_low_relevance_chunks": extraction_stats.dropped_low_relevance_chunks,
                },
                "budget": {
                    "max_total_chars": self.budget.max_total_chars,
                    "max_summary_chars": self.budget.max_summary_chars,
                    "max_chars_per_chunk": self.budget.max_chars_per_chunk,
                    "max_chunks": self.budget.max_chunks,
                    "min_chunk_score": self.budget.min_chunk_score,
                },
                "trusted_input": False,
            },
            warnings=warnings,
        )
        self._audit(ctx, PolicyDecision(Decision.ALLOW, RiskLevel.LOW, ["fetch completed"]), payload, result)
        return result
