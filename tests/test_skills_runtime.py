from __future__ import annotations

from nanocli.models import SkillsOptions
from nanocli.skills_runtime import SkillManager


def test_skill_manager_discovers_builtin_and_filesystem_skills(tmp_path):
    repo = tmp_path / "repo"
    skill_root = repo / ".nanocli" / "skills" / "demo-skill"
    skill_root.mkdir(parents=True, exist_ok=True)
    (skill_root / "SKILL.md").write_text(
        """---
name: demo-skill
description: Demo skill from filesystem
---

# Demo Skill

Use this skill to test local discovery.
""",
        encoding="utf-8",
    )

    manager = SkillManager(repo, SkillsOptions(project_paths=[".nanocli/skills"]))
    catalog = manager.discover()

    assert "travel-weather-briefing" in catalog
    assert "demo-skill" in catalog
    assert catalog["demo-skill"].instructions == "Use this skill to test local discovery."


def test_skill_manager_render_and_install(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    manager = SkillManager(repo, SkillsOptions(enabled=["travel-weather-briefing"]))

    written = manager.render(
        names=["travel-weather-briefing"],
        targets=["chatgpt", "deepseek", "claude-subagent"],
        out_dir=repo / ".nanocli" / "generated",
    )
    installed = manager.install("travel-weather-briefing", repo / ".nanocli" / "skills")

    assert any(path.name == "SKILL.md" for path in written)
    assert any(path.name == "tools.json" for path in written)
    assert any(path.as_posix().endswith("claude-code/travel-weather-briefing.md") for path in written)
    assert (installed / "SKILL.md").exists()
