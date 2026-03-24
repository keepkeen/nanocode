from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from .base import BaseRetriever
from .models import BlockKind, BlockPlane, MemoryBlock, RetrievalHit
from .store import EventSourcedMemoryStore
from .utils import cosine_sparse, lexical_overlap, normalize_terms, rrf_score, sparse_embed


class HybridRetriever(BaseRetriever):
    """Multi-channel retriever.

    Vector and graph are treated as *channels*, not memory truth.
    Final score = weighted fusion across lexical, embedding, graph, salience, stability, and recency.
    """

    def __init__(self, store: EventSourcedMemoryStore) -> None:
        self.store = store

    def retrieve(self, *, namespace: str, query: str, top_k: int) -> List[RetrievalHit]:
        blocks = self.store.list_blocks(namespace)
        query_emb = sparse_embed(query)
        query_terms = set(normalize_terms(query))
        graph_seed = query_terms
        now = datetime.now(timezone.utc)

        rows: List[Tuple[MemoryBlock, Dict[str, float]]] = []
        for block in blocks:
            channels: Dict[str, float] = {}
            channels["lexical"] = lexical_overlap(query, block.text + " " + " ".join(block.tags))
            channels["vector"] = cosine_sparse(query_emb, block.embedding())
            channels["graph"] = self._graph_score(block, graph_seed)
            channels["salience"] = block.salience
            channels["stability"] = block.stability
            age_hours = max(0.0, (now - block.created_at).total_seconds() / 3600.0)
            channels["recency"] = 1.0 / (1.0 + age_hours / 96.0)
            if block.plane == BlockPlane.CONTROL:
                channels["plane_bonus"] = 0.35
            elif block.kind in {BlockKind.PREFERENCE, BlockKind.DECISION, BlockKind.FACT}:
                channels["plane_bonus"] = 0.18
            else:
                channels["plane_bonus"] = 0.0
            rows.append((block, channels))

        if not rows:
            return []

        channel_rankings: Dict[str, Dict[str, int]] = defaultdict(dict)
        for channel in ["lexical", "vector", "graph", "salience", "stability", "recency"]:
            ranked = sorted(rows, key=lambda x: x[1][channel], reverse=True)
            for rank, (block, _) in enumerate(ranked, start=1):
                channel_rankings[channel][block.block_id] = rank

        hits: List[RetrievalHit] = []
        for block, channels in rows:
            ranks = [channel_rankings[ch][block.block_id] for ch in channel_rankings]
            fusion = rrf_score(ranks)
            weighted = (
                0.22 * channels["lexical"]
                + 0.18 * channels["vector"]
                + 0.12 * channels["graph"]
                + 0.18 * channels["salience"]
                + 0.14 * channels["stability"]
                + 0.08 * channels["recency"]
                + channels["plane_bonus"]
                + 0.08 * fusion
            )
            hits.append(
                RetrievalHit(
                    block=block,
                    score=weighted,
                    channel_scores=channels,
                    evidence={"rrf": fusion},
                )
            )

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def _graph_score(self, block: MemoryBlock, query_terms: set[str]) -> float:
        if not query_terms:
            return 0.0
        block_terms = set(normalize_terms(block.text + " " + " ".join(block.tags + block.references)))
        if not block_terms:
            return 0.0
        direct = len(query_terms & block_terms) / max(1, len(query_terms))
        ref_bonus = min(0.3, 0.05 * len(block.references))
        return min(1.0, direct + ref_bonus)
