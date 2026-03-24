from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlparse
import re

from .types import SearchHit
from .utils import extract_domain


TRACKING_QUERY_RE = re.compile(r"(?:^|[?&])(utm_[^=&]+|gclid|fbclid|msclkid|yclid|ref|ref_src|source)=[^&#]*", re.IGNORECASE)
WORD_RE = re.compile(r"[a-z0-9][a-z0-9._+-]{1,}", re.IGNORECASE)

_DEFAULT_HIGH_TRUST_DOMAINS = {
    "github.com",
    "docs.github.com",
    "arxiv.org",
    "openreview.net",
    "acm.org",
    "dl.acm.org",
    "ieeexplore.ieee.org",
    "anthropic.com",
    "platform.openai.com",
    "developers.openai.com",
    "docs.python.org",
    "pypi.org",
    "mozilla.org",
    "w3.org",
    "developer.mozilla.org",
}

_DEFAULT_LOW_TRUST_HINTS = {
    "medium.com",
    "quora.com",
    "pinterest.com",
    "stackoverflow.blog",
}

_AD_HINTS = {
    "sponsored",
    "promoted",
    "ad",
    "ads",
    "shopping",
    "deal",
    "coupon",
    "affiliate",
}

_RESULT_TYPE_HINTS = {
    "shopping": [r"/product", r"/shop", r"/store", r"\bprice\b", r"\bbuy\b"],
    "video": [r"youtube\.com", r"vimeo\.com", r"bilibili\.com", r"\bwatch\b", r"\bvideo\b"],
    "forum": [r"reddit\.com", r"news\.ycombinator\.com", r"discuss", r"forum"],
    "docs": [r"/docs", r"documentation", r"readthedocs", r"/manual"],
    "repo": [r"github\.com/.+/.+", r"gitlab\.com/.+/.+", r"sourcehut", r"codeberg"],
}


@dataclass(slots=True)
class SearchFilterConfig:
    top_k: int = 6
    min_relevance_score: float = 0.08
    preferred_result_types: list[str] = field(default_factory=lambda: ["docs", "repo", "article", "forum"])
    blocked_result_types: list[str] = field(default_factory=lambda: ["shopping"])
    high_trust_domains: set[str] = field(default_factory=lambda: set(_DEFAULT_HIGH_TRUST_DOMAINS))
    low_trust_domain_hints: set[str] = field(default_factory=lambda: set(_DEFAULT_LOW_TRUST_HINTS))
    strip_tracking_params: bool = True


@dataclass(slots=True)
class SearchFilterStats:
    input_count: int = 0
    kept_count: int = 0
    dropped_ads: int = 0
    dropped_irrelevant: int = 0
    dropped_duplicates: int = 0
    dropped_low_relevance: int = 0
    dropped_policy: int = 0


class SearchResultFilter:
    def __init__(self, config: SearchFilterConfig | None = None) -> None:
        self.config = config or SearchFilterConfig()

    def filter(
        self,
        hits: Iterable[SearchHit],
        *,
        query: str,
        normalize_url,
    ) -> tuple[list[SearchHit], SearchFilterStats]:
        stats = SearchFilterStats()
        results: list[SearchHit] = []
        seen: set[str] = set()
        query_terms = _query_terms(query)

        for hit in hits:
            stats.input_count += 1
            if self._looks_like_ad(hit):
                stats.dropped_ads += 1
                continue

            normalized, allowed = normalize_url(hit.url)
            if not normalized or not allowed:
                stats.dropped_policy += 1
                continue

            canonical = _canonical_url(normalized, strip_tracking=self.config.strip_tracking_params)
            if canonical in seen:
                stats.dropped_duplicates += 1
                continue
            seen.add(canonical)

            result_type = _classify_result_type(hit)
            if result_type in self.config.blocked_result_types:
                stats.dropped_irrelevant += 1
                continue

            relevance = _relevance_score(query_terms, hit)
            quality = _quality_score(canonical, hit, result_type, self.config)
            combined = relevance * 0.65 + quality * 0.35
            if combined < self.config.min_relevance_score:
                stats.dropped_low_relevance += 1
                continue

            hit.url = canonical
            hit.metadata = dict(hit.metadata)
            hit.metadata.update(
                {
                    "result_type": result_type,
                    "relevance_score": round(relevance, 4),
                    "quality_score": round(quality, 4),
                    "combined_score": round(combined, 4),
                    "domain": extract_domain(canonical),
                }
            )
            results.append(hit)

        results.sort(key=lambda item: (
            -float(item.metadata.get("combined_score", 0.0)),
            -float(item.score or 0.0),
            item.url,
        ))
        results = results[: self.config.top_k]
        stats.kept_count = len(results)
        return results, stats

    def _looks_like_ad(self, hit: SearchHit) -> bool:
        metadata = {str(k).lower(): str(v).lower() for k, v in (hit.metadata or {}).items()}
        if any(key in metadata for key in ("ad", "ads", "ad_results", "sponsored", "promoted")):
            return True
        hay = " ".join([hit.title, hit.snippet, hit.url, " ".join(metadata.values())]).lower()
        return any(token in hay for token in _AD_HINTS)



def _canonical_url(url: str, *, strip_tracking: bool) -> str:
    if not strip_tracking:
        return url
    parsed = urlparse(url)
    query = TRACKING_QUERY_RE.sub("", parsed.query)
    query = query.strip("&")
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path, query=query, fragment="").geturl()



def _query_terms(query: str) -> list[str]:
    return [term.lower() for term in WORD_RE.findall(query) if len(term) >= 2]



def _classify_result_type(hit: SearchHit) -> str:
    hay = f"{hit.title} {hit.snippet} {hit.url}".lower()
    for result_type, patterns in _RESULT_TYPE_HINTS.items():
        for pattern in patterns:
            if re.search(pattern, hay):
                return result_type
    return "article"



def _relevance_score(query_terms: list[str], hit: SearchHit) -> float:
    if not query_terms:
        return 0.5
    title = hit.title.lower()
    snippet = hit.snippet.lower()
    url = hit.url.lower()
    coverage = 0.0
    for term in query_terms:
        if term in title:
            coverage += 1.8
        elif term in snippet:
            coverage += 1.0
        elif term in url:
            coverage += 0.5
    max_score = max(1.0, len(query_terms) * 1.8)
    return min(1.0, coverage / max_score)



def _quality_score(url: str, hit: SearchHit, result_type: str, config: SearchFilterConfig) -> float:
    domain = extract_domain(url)
    score = 0.35
    if domain in config.high_trust_domains or any(domain.endswith("." + d) for d in config.high_trust_domains):
        score += 0.35
    if domain in config.low_trust_domain_hints or any(domain.endswith("." + d) for d in config.low_trust_domain_hints):
        score -= 0.15
    if result_type in config.preferred_result_types:
        score += 0.15
    if hit.published_at:
        score += 0.05
    if hit.score is not None:
        try:
            score += min(0.10, max(0.0, float(hit.score)) * 0.10)
        except (TypeError, ValueError):
            pass
    return max(0.0, min(1.0, score))
