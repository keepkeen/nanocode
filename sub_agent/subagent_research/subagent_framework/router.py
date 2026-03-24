from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

from .abstractions import AbstractRouter, AbstractSubAgent
from .models import DelegationDecision, TaskEnvelope


class KeywordCapabilityRouter(AbstractRouter):
    """A simple but extensible router.

    It encodes three ideas drawn from recent agent research and tooling practice:
    - task decomposition through explicit capability matching,
    - context isolation via top-k delegation rather than broadcasting to every agent,
    - token efficiency via pruning low-utility candidates.
    """

    def __init__(self, min_score: float = 0.8, max_parallel_agents: int = 2) -> None:
        self.min_score = min_score
        self.max_parallel_agents = max_parallel_agents

    def decide(self, task: TaskEnvelope, agents: Sequence[AbstractSubAgent]) -> DelegationDecision:
        query_terms = self._normalize(task.user_query)
        scores = {}
        for agent in agents:
            if not agent.can_handle(task):
                scores[agent.definition.name] = 0.0
                continue
            agent_terms = self._normalize(
                " ".join(
                    [
                        agent.definition.name,
                        agent.definition.description,
                        agent.definition.instructions,
                        *agent.definition.tags,
                        *agent.definition.capabilities,
                    ]
                )
            )
            overlap = sum((query_terms & agent_terms).values())
            specificity_bonus = math.log(len(agent.definition.capabilities) + len(agent.definition.tags) + 2)
            scores[agent.definition.name] = round(overlap + specificity_bonus, 3)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        kept = [name for name, score in ranked if score >= self.min_score]

        if not kept and ranked:
            kept = [ranked[0][0]]

        selected = kept[: self.max_parallel_agents]
        parallel = len(selected) > 1
        reason = (
            "parallel delegation based on capability overlap"
            if parallel
            else "single best-matching specialist selected"
        )
        return DelegationDecision(
            selected_agents=selected,
            parallel=parallel,
            reason=reason,
            scores=dict(scores),
        )

    @staticmethod
    def _normalize(text: str) -> Counter[str]:
        tokens = re.findall(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+", text.lower())
        return Counter(tokens)
