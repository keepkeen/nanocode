from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib import parse, request
from urllib.error import HTTPError, URLError
import json
import os
import ssl

from .audit import AuditLogger
from .base import AgentTool, SearchProvider
from .policy import PolicyDecision, SecurityPolicy
from .search_filters import SearchFilterConfig, SearchResultFilter
from .types import Decision, SearchHit, RiskLevel, ToolContext, ToolName, ToolResult, WarningItem


class _JsonHttpClient:
    def __init__(self, user_agent: str = "optimized-agent-tools/0.2") -> None:
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
            results.append(
                SearchHit(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", ""),
                    source=self.provider_name,
                    metadata={
                        "profile": item.get("profile", {}),
                        "family_friendly": item.get("family_friendly"),
                        "language": item.get("language"),
                    },
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
                    metadata={"raw_score": item.get("score")},
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
            score = getattr(item, "score", None) or item.get("score")
            results.append(
                SearchHit(
                    title=title,
                    url=url,
                    snippet=text[:600],
                    score=score,
                    source=self.provider_name,
                    metadata={"raw_score": score},
                )
            )
        return results


class SecureWebSearchTool(AgentTool):
    name = ToolName.WEBSEARCH.value

    def __init__(
        self,
        *,
        policy: SecurityPolicy,
        provider: SearchProvider,
        audit: AuditLogger | None = None,
        result_filter: SearchResultFilter | None = None,
    ) -> None:
        self.policy = policy
        self.provider = provider
        self.audit = audit
        self.result_filter = result_filter or SearchResultFilter(SearchFilterConfig())

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
        limit = int(kwargs.get("limit", 8))
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

        decision = PolicyDecision(Decision.ASK, RiskLevel.MEDIUM, ["repeated identical search pattern detected"]) if call_count >= 3 else PolicyDecision(Decision.ALLOW, RiskLevel.LOW, ["query allowed"])

        try:
            raw_hits = self.provider.search(query, limit=limit, include_domains=include_domains, exclude_domains=exclude_domains)
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

        def normalize_candidate(url: str) -> tuple[str | None, bool]:
            normalized, url_decision = self.policy.decide_url(url, tool=ToolName.WEBSEARCH)
            return normalized, bool(normalized and url_decision.decision != Decision.DENY)

        filtered_hits, stats = self.result_filter.filter(raw_hits, query=query, normalize_url=normalize_candidate)
        warnings: list[WarningItem] = []
        if call_count >= 3:
            warnings.append(WarningItem(code="websearch_repeat_pattern", message="repeated identical search pattern detected", risk=RiskLevel.MEDIUM))
        if stats.dropped_ads:
            warnings.append(WarningItem(code="websearch_ads_filtered", message=f"filtered {stats.dropped_ads} ad or sponsored results", risk=RiskLevel.LOW))
        if stats.dropped_duplicates:
            warnings.append(WarningItem(code="websearch_duplicates_filtered", message=f"filtered {stats.dropped_duplicates} duplicate results", risk=RiskLevel.LOW))
        if not filtered_hits:
            warnings.append(WarningItem(code="websearch_no_results", message="no result survived filtering", risk=RiskLevel.MEDIUM))

        if session_state is not None:
            session_state.remember_urls([item.url for item in filtered_hits])

        results_payload = []
        for hit in filtered_hits:
            results_payload.append(
                {
                    "title": hit.title,
                    "url": hit.url,
                    "snippet": hit.snippet,
                    "score": hit.score,
                    "source": hit.source,
                    "published_at": hit.published_at,
                    "metadata": hit.metadata,
                }
            )

        result = ToolResult(
            ok=True,
            tool=ToolName.WEBSEARCH,
            summary=f"search returned {len(filtered_hits)} filtered results",
            data={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "provider": self.provider.provider_name,
                "query": query,
                "results": results_payload,
                "filtering": {
                    "input_count": stats.input_count,
                    "kept_count": stats.kept_count,
                    "dropped_ads": stats.dropped_ads,
                    "dropped_irrelevant": stats.dropped_irrelevant,
                    "dropped_duplicates": stats.dropped_duplicates,
                    "dropped_low_relevance": stats.dropped_low_relevance,
                    "dropped_policy": stats.dropped_policy,
                },
            },
            warnings=warnings,
        )
        self._audit(ctx, decision, payload, result)
        return result
