from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib import request, parse
from urllib.error import URLError, HTTPError
import json
import os
import ssl

from .audit import AuditLogger
from .base import AgentTool, SearchProvider
from .policy import PolicyDecision, SecurityPolicy
from .types import Decision, SearchHit, RiskLevel, ToolContext, ToolName, ToolResult, WarningItem
from .utils import extract_domain


class _JsonHttpClient:
    def __init__(self, user_agent: str = "optimized-agent-tools/0.1") -> None:
        self.user_agent = user_agent
        self.ssl_ctx = ssl.create_default_context()
        self.opener = request.build_opener(request.HTTPSHandler(context=self.ssl_ctx))
        self.opener.addheaders = [("User-Agent", user_agent)]

    def get_json(self, url: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        final_url = url
        if params:
            final_url += ("&" if "?" in final_url else "?") + parse.urlencode(params, doseq=True)
        req = request.Request(final_url, headers=headers or {}, method="GET")
        with self.opener.open(req, timeout=20) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8", errors="replace"))

    def post_json(self, url: str, *, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = json.dumps(body or {}).encode("utf-8")
        req_headers = {"Content-Type": "application/json", **(headers or {})}
        req = request.Request(url, headers=req_headers, method="POST", data=payload)
        with self.opener.open(req, timeout=20) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8", errors="replace"))


class BraveSearchProvider(SearchProvider):
    provider_name = "brave"

    def __init__(self, api_key: str | None = None, client: _JsonHttpClient | None = None) -> None:
        self.api_key = api_key or os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("BRAVE_API_KEY")
        self.client = client or _JsonHttpClient()
        if not self.api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY is required")

    def search(self, query: str, *, limit: int = 5, include_domains: list[str] | None = None, exclude_domains: list[str] | None = None):
        params: dict[str, Any] = {"q": query, "count": max(1, min(limit, 20))}
        if include_domains:
            params["site"] = ",".join(include_domains)
        data = self.client.get_json(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": self.api_key},
            params=params,
        )
        results: list[SearchHit] = []
        for item in data.get("web", {}).get("results", []):
            url = item.get("url", "")
            domain = extract_domain(url)
            if exclude_domains and any(domain == d or domain.endswith("." + d) for d in exclude_domains):
                continue
            results.append(
                SearchHit(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("description", ""),
                    source=self.provider_name,
                    metadata={"profile": item.get("profile", {})},
                )
            )
        return results


class TavilySearchProvider(SearchProvider):
    provider_name = "tavily"

    def __init__(self, api_key: str | None = None, client: _JsonHttpClient | None = None) -> None:
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.client = client or _JsonHttpClient()
        if not self.api_key:
            raise RuntimeError("TAVILY_API_KEY is required")

    def search(self, query: str, *, limit: int = 5, include_domains: list[str] | None = None, exclude_domains: list[str] | None = None):
        body: dict[str, Any] = {"query": query, "max_results": max(1, min(limit, 20))}
        if include_domains:
            body["include_domains"] = include_domains
        if exclude_domains:
            body["exclude_domains"] = exclude_domains
        data = self.client.post_json(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {self.api_key}"},
            body=body,
        )
        results: list[SearchHit] = []
        for item in data.get("results", []):
            results.append(
                SearchHit(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    score=item.get("score"),
                    published_at=item.get("published_date"),
                    source=self.provider_name,
                )
            )
        return results


class ExaSearchProvider(SearchProvider):
    provider_name = "exa"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        try:
            from exa_py import Exa  # type: ignore
        except Exception as exc:
            raise RuntimeError("exa-py is required for ExaSearchProvider") from exc
        if not self.api_key:
            raise RuntimeError("EXA_API_KEY is required")
        self._client = Exa(self.api_key)

    def search(self, query: str, *, limit: int = 5, include_domains: list[str] | None = None, exclude_domains: list[str] | None = None):
        kwargs: dict[str, Any] = {"num_results": max(1, min(limit, 20))}
        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains
        data = self._client.search_and_contents(query, text=True, **kwargs)
        items = getattr(data, "results", data.get("results", []))
        results: list[SearchHit] = []
        for item in items:
            title = getattr(item, "title", None) or item.get("title", "")
            url = getattr(item, "url", None) or item.get("url", "")
            text = getattr(item, "text", None) or item.get("text", "")
            results.append(SearchHit(title=title, url=url, snippet=text[:500], source=self.provider_name))
        return results


class SecureWebSearchTool(AgentTool):
    name = ToolName.WEBSEARCH.value

    def __init__(self, *, policy: SecurityPolicy, provider: SearchProvider, audit: AuditLogger | None = None) -> None:
        self.policy = policy
        self.provider = provider
        self.audit = audit

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
        query = str(kwargs.get("query", "")).strip()
        limit = int(kwargs.get("limit", 5))
        include_domains = list(kwargs.get("include_domains") or [])
        exclude_domains = list(kwargs.get("exclude_domains") or [])
        session_state = kwargs.get("session_state")
        call_count = int(kwargs.get("call_count", 1))

        payload = {
            "query": query,
            "limit": limit,
            "include_domains": include_domains,
            "exclude_domains": exclude_domains,
            "provider": self.provider.provider_name,
        }
        if not query:
            decision = PolicyDecision(Decision.DENY, RiskLevel.MEDIUM, ["empty query is not allowed"])
            result = ToolResult(
                ok=False,
                tool=ToolName.WEBSEARCH,
                summary="empty query",
                data={"timestamp": datetime.now(timezone.utc).isoformat()},
                warnings=[WarningItem(code="websearch_empty", message=decision.reasons[0], risk=decision.risk)],
            )
            self._audit(ctx, decision, payload, result)
            return result
        if call_count >= 3:
            decision = PolicyDecision(Decision.ASK, RiskLevel.MEDIUM, ["repeated identical search pattern detected"])
        else:
            decision = PolicyDecision(Decision.ALLOW, RiskLevel.LOW, ["query allowed"])

        try:
            hits = self.provider.search(query, limit=limit, include_domains=include_domains, exclude_domains=exclude_domains)
        except (HTTPError, URLError, RuntimeError, ValueError) as exc:
            result = ToolResult(
                ok=False,
                tool=ToolName.WEBSEARCH,
                summary="search provider error",
                data={"timestamp": datetime.now(timezone.utc).isoformat(), "provider": self.provider.provider_name},
                warnings=[WarningItem(code="websearch_provider_error", message=str(exc), risk=RiskLevel.MEDIUM)],
            )
            self._audit(ctx, PolicyDecision(Decision.ALLOW, RiskLevel.LOW, ["search attempted"]), payload, result)
            return result

        deduped: list[SearchHit] = []
        seen: set[str] = set()
        warnings: list[WarningItem] = []
        for hit in hits:
            normalized, url_decision = self.policy.decide_url(hit.url, tool=ToolName.WEBSEARCH)
            if not normalized or url_decision.decision == Decision.DENY:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            hit.url = normalized
            deduped.append(hit)
        if not deduped:
            warnings.append(WarningItem(code="websearch_no_results", message="no policy-compliant results returned", risk=RiskLevel.LOW))

        if session_state is not None:
            session_state.remember_urls([item.url for item in deduped])

        result = ToolResult(
            ok=True,
            tool=ToolName.WEBSEARCH,
            summary="search completed",
            data={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "provider": self.provider.provider_name,
                "query": query,
                "results": [
                    {
                        "title": item.title,
                        "url": item.url,
                        "snippet": item.snippet,
                        "score": item.score,
                        "source": item.source,
                        "published_at": item.published_at,
                        "metadata": item.metadata,
                    }
                    for item in deduped
                ],
            },
            warnings=warnings,
        )
        self._audit(ctx, decision, payload, result)
        return result
