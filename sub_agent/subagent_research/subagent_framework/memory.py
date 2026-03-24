from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .abstractions import AbstractMemory
from .models import MemoryEntry, WorkingMemorySnapshot


class HierarchicalWorkingMemory(AbstractMemory):
    """A lightweight hierarchical memory inspired by HiAgent.

    Design intent:
    1. Keep active subgoal observations small and directly accessible.
    2. Archive other subgoals into compact summaries to avoid prompt bloat.
    3. Allow the orchestrator to hand each sub-agent a focused memory snapshot.
    """

    def __init__(self, max_active_entries: int = 6) -> None:
        self.max_active_entries = max_active_entries
        self._entries_by_subgoal: Dict[str, List[MemoryEntry]] = defaultdict(list)
        self._archived_summaries: Dict[str, str] = {}

    def remember(self, agent_name: str, subgoal: str, observation: str) -> None:
        entry = MemoryEntry(
            subgoal=subgoal,
            observation=f"[{agent_name}] {observation}",
        )
        bucket = self._entries_by_subgoal[subgoal]
        bucket.append(entry)
        if len(bucket) > self.max_active_entries:
            self._archive_oldest(subgoal)

    def _archive_oldest(self, subgoal: str) -> None:
        bucket = self._entries_by_subgoal[subgoal]
        oldest = bucket.pop(0)
        current = self._archived_summaries.get(subgoal, "")
        addition = oldest.compact_summary or oldest.observation
        self._archived_summaries[subgoal] = (current + "\n" + addition).strip()

    def snapshot(self, active_subgoal: str | None = None) -> WorkingMemorySnapshot:
        active_entries = list(self._entries_by_subgoal.get(active_subgoal or "", []))
        return WorkingMemorySnapshot(
            active_subgoal=active_subgoal,
            active_entries=active_entries,
            archived_summaries=dict(self._archived_summaries),
        )
