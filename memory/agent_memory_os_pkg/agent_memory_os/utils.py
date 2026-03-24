from __future__ import annotations

from collections import Counter
from math import sqrt
from typing import Any, Dict, Iterable, List
import hashlib
import json
import re

TERM_RE = re.compile(r"[a-zA-Z0-9_\-\./]{2,}")
STOP_WORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "at", "by", "from", "is", "are",
    "be", "as", "it", "we", "i", "you", "they", "he", "she", "this", "that", "with", "your", "our",
    "my", "their", "will", "should", "can", "could", "would", "into", "about",
}


def normalize_space(text: str) -> str:
    return " ".join((text or "").split())


def normalize_terms(text: str) -> List[str]:
    terms = [t.lower() for t in TERM_RE.findall(text or "")]
    return [t for t in terms if t not in STOP_WORDS]


def sparse_embed(text: str) -> Dict[str, float]:
    counts = Counter(normalize_terms(text))
    if not counts:
        return {}
    norm = sqrt(sum(v * v for v in counts.values())) or 1.0
    return {k: v / norm for k, v in counts.items()}


def cosine_sparse(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def lexical_overlap(a: str, b: str) -> float:
    ta = set(normalize_terms(a))
    tb = set(normalize_terms(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta))


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def content_address(data: Any) -> str:
    return sha256_text(stable_json(data))


def top_terms(text: str, limit: int = 8) -> List[str]:
    seen = []
    for term in normalize_terms(text):
        if term not in seen:
            seen.append(term)
        if len(seen) >= limit:
            break
    return seen


def first_sentence(text: str, limit: int = 240) -> str:
    text = normalize_space(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def rrf_score(ranks: Iterable[int], k: int = 60) -> float:
    return sum(1.0 / (k + r) for r in ranks)
