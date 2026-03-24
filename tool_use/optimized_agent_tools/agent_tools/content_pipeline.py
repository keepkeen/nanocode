from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from typing import Iterable
import math
import re


@dataclass(slots=True)
class EvidenceChunk:
    text: str
    score: float
    start: int = 0
    end: int = 0
    query_hits: int = 0


@dataclass(slots=True)
class ExtractionStats:
    raw_chars: int = 0
    visible_chars: int = 0
    dropped_boilerplate_blocks: int = 0
    dropped_low_relevance_chunks: int = 0


@dataclass(slots=True)
class BudgetConfig:
    max_total_chars: int = 9000
    max_summary_chars: int = 1000
    max_chars_per_chunk: int = 1200
    max_chunks: int = 5
    min_chunk_score: float = 0.08


class MainContentExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._ignore_depth = 0
        self._boiler_depth = 0
        self.dropped_boilerplate_blocks = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attrs_map = {str(k).lower(): str(v).lower() for k, v in attrs}
        attrs_blob = " ".join(attrs_map.values())
        if tag in {"script", "style", "noscript", "svg", "canvas", "iframe", "template"}:
            self._ignore_depth += 1
            return
        if tag in {"nav", "footer", "aside", "form"} or _looks_boilerplate(attrs_blob):
            self._boiler_depth += 1
            self.dropped_boilerplate_blocks += 1
            return
        if tag in {"header"} and _looks_boilerplate(attrs_blob):
            self._boiler_depth += 1
            self.dropped_boilerplate_blocks += 1
            return
        if tag in {"article", "section", "div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas", "iframe", "template"} and self._ignore_depth:
            self._ignore_depth -= 1
            return
        if tag in {"nav", "footer", "aside", "form", "header", "section", "article", "div", "p", "li"} and self._boiler_depth:
            self._boiler_depth -= 1
            return
        if tag in {"article", "section", "div", "p", "li"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignore_depth or self._boiler_depth:
            return
        clean = re.sub(r"\s+", " ", data).strip()
        if clean:
            self._chunks.append(clean + " ")

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = unescape(raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


class QueryChunkRanker:
    def __init__(self, *, chunk_size: int = 1100, overlap: int = 120) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def rank(self, text: str, query: str) -> list[EvidenceChunk]:
        chunks = _split_into_chunks(text, chunk_size=self.chunk_size, overlap=self.overlap)
        terms = _query_terms(query)
        scored: list[EvidenceChunk] = []
        for start, end, chunk in chunks:
            score, hits = _chunk_score(chunk, terms)
            scored.append(EvidenceChunk(text=chunk, score=score, start=start, end=end, query_hits=hits))
        scored.sort(key=lambda item: (-item.score, -item.query_hits, item.start))
        return scored


class ContextBudgetManager:
    def __init__(self, config: BudgetConfig | None = None) -> None:
        self.config = config or BudgetConfig()

    def package(self, title: str, text: str, ranked_chunks: Iterable[EvidenceChunk]) -> tuple[str, list[EvidenceChunk], ExtractionStats]:
        stats = ExtractionStats(raw_chars=len(text), visible_chars=len(text))
        summary = _summarize_text(title, text, max_chars=self.config.max_summary_chars)
        kept: list[EvidenceChunk] = []
        used = len(summary)
        for chunk in ranked_chunks:
            if chunk.score < self.config.min_chunk_score:
                stats.dropped_low_relevance_chunks += 1
                continue
            clipped = _clip_text(chunk.text, self.config.max_chars_per_chunk)
            new_chunk = EvidenceChunk(text=clipped, score=chunk.score, start=chunk.start, end=chunk.end, query_hits=chunk.query_hits)
            projected = used + len(clipped)
            if len(kept) >= self.config.max_chunks or projected > self.config.max_total_chars:
                stats.dropped_low_relevance_chunks += 1
                continue
            kept.append(new_chunk)
            used = projected
        if not kept and text:
            fallback = _clip_text(text, min(self.config.max_chars_per_chunk, self.config.max_total_chars - len(summary)))
            if fallback:
                kept.append(EvidenceChunk(text=fallback, score=0.01, start=0, end=len(fallback), query_hits=0))
        return summary, kept, stats



def extract_and_rank(html_or_text: str, query: str, *, is_html: bool, budget: BudgetConfig | None = None) -> tuple[str, list[EvidenceChunk], ExtractionStats]:
    extractor_stats = ExtractionStats(raw_chars=len(html_or_text))
    if is_html:
        parser = MainContentExtractor()
        parser.feed(html_or_text)
        visible = parser.text()
        extractor_stats.dropped_boilerplate_blocks = parser.dropped_boilerplate_blocks
    else:
        visible = _normalize_text(html_or_text)
    extractor_stats.visible_chars = len(visible)
    manager = ContextBudgetManager(budget)
    ranker = QueryChunkRanker(chunk_size=min(manager.config.max_chars_per_chunk + 200, 1400))
    summary, chunks, package_stats = manager.package("", visible, ranker.rank(visible, query))
    package_stats.raw_chars = extractor_stats.raw_chars
    package_stats.visible_chars = extractor_stats.visible_chars
    package_stats.dropped_boilerplate_blocks = extractor_stats.dropped_boilerplate_blocks
    return summary, chunks, package_stats



def _looks_boilerplate(attrs_blob: str) -> bool:
    return any(token in attrs_blob for token in [
        "footer",
        "sidebar",
        "recommend",
        "subscribe",
        "newsletter",
        "cookie",
        "consent",
        "comment",
        "share",
        "social",
        "promo",
        "advert",
        "breadcrumb",
        "related",
        "login",
        "signup",
    ])



def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()



def _query_terms(query: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[a-zA-Z0-9_+.-]{2,}", query) if len(term) >= 2]



def _split_into_chunks(text: str, *, chunk_size: int, overlap: int) -> list[tuple[int, int, str]]:
    text = _normalize_text(text)
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[tuple[int, int, str]] = []
    cursor = 0
    current = ""
    start = 0
    for para in paragraphs:
        piece = para if not current else current + "\n\n" + para
        if len(piece) <= chunk_size:
            if not current:
                start = cursor
            current = piece
            cursor += len(para) + 2
            continue
        if current:
            end = start + len(current)
            chunks.append((start, end, current))
            if overlap > 0:
                tail = current[-overlap:]
                current = tail + "\n\n" + para
                start = max(0, end - len(tail))
            else:
                current = para
                start = cursor
        else:
            for i in range(0, len(para), max(1, chunk_size - overlap)):
                sub = para[i : i + chunk_size]
                chunks.append((cursor + i, cursor + i + len(sub), sub))
            current = ""
            start = cursor + len(para)
        cursor += len(para) + 2
    if current:
        chunks.append((start, start + len(current), current))
    return chunks



def _chunk_score(chunk: str, query_terms: list[str]) -> tuple[float, int]:
    if not chunk:
        return 0.0, 0
    if not query_terms:
        return min(1.0, len(chunk) / 1600.0), 0
    lowered = chunk.lower()
    hits = 0
    tf = 0.0
    distinct = 0
    for term in query_terms:
        count = lowered.count(term)
        if count > 0:
            distinct += 1
            hits += count
            tf += 1.0 + math.log(1 + count)
    if hits == 0:
        return 0.0, 0
    coverage = distinct / max(1, len(query_terms))
    density = min(1.0, hits / max(1, len(chunk) / 120.0))
    score = min(1.0, coverage * 0.65 + density * 0.35 + min(0.1, tf / 20.0))
    return score, hits



def _summarize_text(title: str, text: str, *, max_chars: int) -> str:
    prefix = (title.strip() + "\n\n") if title.strip() else ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chosen = []
    used = len(prefix)
    for para in paragraphs[:4]:
        sentence = para
        if used + len(sentence) > max_chars:
            break
        chosen.append(sentence)
        used += len(sentence) + 2
    summary = prefix + "\n\n".join(chosen)
    return _clip_text(summary or text, max_chars)



def _clip_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"
