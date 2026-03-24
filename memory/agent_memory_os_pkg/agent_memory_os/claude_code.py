from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .models import BlockKind, BlockPlane, MemoryBlock


@dataclass(slots=True)
class ClaudeCodeMemoryExporter:
    claude_md_title: str = "# Project Instructions for Claude Code"
    memory_md_title: str = "# Auto Memory Snapshot"
    imported_paths: List[str] = field(default_factory=list)

    def render_claude_md(self, control_blocks: List[MemoryBlock]) -> str:
        lines = [self.claude_md_title, ""]
        for block in control_blocks:
            if block.plane != BlockPlane.CONTROL:
                continue
            lines.append(f"- [{block.kind.value}] {block.text}")
        if self.imported_paths:
            lines.extend(["", "## Imports"])
            lines.extend([f"- @{p}" for p in self.imported_paths])
        return "\n".join(lines).strip() + "\n"

    def render_memory_md(self, blocks: List[MemoryBlock], max_lines: int = 200) -> str:
        lines = [self.memory_md_title, ""]
        ranked = sorted(blocks, key=lambda b: (b.plane.value != BlockPlane.CONTROL.value, -b.salience, -b.stability))
        for block in ranked:
            lines.append(f"- [{block.plane.value}/{block.kind.value}] {block.text}")
            if len(lines) >= max_lines:
                break
        return "\n".join(lines).strip() + "\n"

    def export(self, root: str | Path, control_blocks: List[MemoryBlock], all_blocks: List[MemoryBlock]) -> dict[str, str]:
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        claude_md = root / "CLAUDE.md"
        auto_dir = root / ".claude" / "memory"
        auto_dir.mkdir(parents=True, exist_ok=True)
        memory_md = auto_dir / "MEMORY.md"
        claude_md.write_text(self.render_claude_md(control_blocks), encoding="utf-8")
        memory_md.write_text(self.render_memory_md(all_blocks), encoding="utf-8")
        return {"claude_md": str(claude_md), "memory_md": str(memory_md)}
