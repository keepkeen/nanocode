from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .models import MemoryRecord, MemoryTier


@dataclass
class ClaudeCodeProjectMemory:
    """Exports agent memory into Claude Code friendly project files."""

    project_name: str
    coding_rules: List[str] = field(default_factory=list)
    workflow_rules: List[str] = field(default_factory=list)
    memories: List[MemoryRecord] = field(default_factory=list)

    def render_claude_md(self) -> str:
        parts = [f"# {self.project_name} - CLAUDE.md", "", "## Project Rules"]
        if not self.coding_rules and not self.workflow_rules:
            parts.append("- Keep responses concise, deterministic, and test-backed.")
        for rule in self.coding_rules:
            parts.append(f"- {rule}")
        if self.workflow_rules:
            parts.extend(["", "## Workflow"])
            for rule in self.workflow_rules:
                parts.append(f"- {rule}")
        return "\n".join(parts).strip() + "\n"

    def render_memory_md(self, max_lines: int = 200) -> str:
        ordered = sorted(
            self.memories,
            key=lambda m: (
                0 if m.tier in {MemoryTier.PINNED, MemoryTier.INSTRUCTION} else 1,
                -(m.salience + m.durability),
            ),
        )
        lines = [f"# {self.project_name} - MEMORY.md", "", "## Auto memory"]
        for memory in ordered:
            lines.append(f"- [{memory.kind.value}/{memory.tier.value}] {memory.text}")
            if len(lines) >= max_lines:
                break
        return "\n".join(lines).strip() + "\n"
