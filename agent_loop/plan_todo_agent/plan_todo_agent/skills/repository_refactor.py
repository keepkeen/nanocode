from __future__ import annotations

from typing import List

from plan_todo_agent.core.interfaces import BaseSkill
from plan_todo_agent.core.schemas import Plan, PlanStep, SkillContext, StepKind, ToolSpec


class RepositoryRefactorSkill(BaseSkill):
    """Concrete skill example for long-horizon coding/refactor tasks."""

    @property
    def context(self) -> SkillContext:
        return SkillContext(
            name="repository-refactor",
            description="Plan and execute a multi-file repository refactor with dependency awareness, verification, and explicit rollback thinking.",
            success_definition=[
                "The root cause or desired architecture is identified before broad edits begin.",
                "Edits preserve backward compatibility or include a migration note.",
                "Verification is explicit: tests, static checks, or contract checks are named.",
                "The final result contains user-visible deliverables rather than only intermediate analysis.",
            ],
            planning_hints=[
                "Prefer read-first exploration, then targeted edits.",
                "Separate repo understanding from implementation and verification.",
                "Keep the active todo frontier short, usually 3-5 items.",
                "If a blocker appears, mark the step blocked instead of silently changing strategy.",
            ],
            extra_instructions=[
                "Always identify affected files before proposing risky edits.",
                "Call verification tools before claiming success.",
            ],
        )

    def build_tools(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="search_codebase",
                description="Search the repository for symbols, files, patterns, or configuration references.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query or symbol name"},
                        "path": {"type": "string", "description": "Optional subdirectory scope"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
                read_only=True,
            ),
            ToolSpec(
                name="read_file",
                description="Read a file to inspect implementation details.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path of file to read"},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                read_only=True,
            ),
            ToolSpec(
                name="edit_file",
                description="Apply a targeted edit to a file.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "instruction": {"type": "string", "description": "Precise edit instruction"},
                    },
                    "required": ["path", "instruction"],
                    "additionalProperties": False,
                },
            ),
            ToolSpec(
                name="run_checks",
                description="Run tests, type checks, lint, or build commands to validate changes.",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command used for verification"},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            ),
        ]

    def bootstrap_plan(self, objective: str) -> Plan:
        return Plan(
            goal=objective,
            assumptions=[
                "The repository is available locally or through a connected coding environment.",
                "Read and edit tools are available.",
            ],
            constraints=[
                "Do not skip verification.",
                "Prefer minimal, dependency-aware edits over broad rewrites.",
            ],
            deliverables=[
                "A stable implementation plan",
                "Verified code changes or an explicit blocker report",
                "A concise delivery summary",
            ],
            steps=[
                PlanStep(
                    step_id="S1",
                    title="Map the affected surface area",
                    description="Identify files, symbols, config, tests, and interfaces impacted by the requested change.",
                    kind=StepKind.SEARCH,
                    success_criteria=[
                        "Primary files and interfaces are identified.",
                        "Potential blast radius is documented.",
                    ],
                    suggested_tools=["search_codebase", "read_file"],
                    risk_notes=["Missing a secondary integration point can invalidate later edits."],
                    estimated_cost="low",
                ),
                PlanStep(
                    step_id="S2",
                    title="Design the minimal refactor path",
                    description="Create a dependency-aware implementation path with compatibility and rollback considerations.",
                    kind=StepKind.ANALYZE,
                    depends_on=["S1"],
                    success_criteria=[
                        "Dependencies and ordering are explicit.",
                        "Verification strategy is specified.",
                    ],
                    suggested_tools=["read_file"],
                    risk_notes=["Broad rewrites increase regression risk."],
                    estimated_cost="medium",
                ),
                PlanStep(
                    step_id="S3",
                    title="Apply targeted code changes",
                    description="Edit only the necessary files using the agreed refactor path.",
                    kind=StepKind.IMPLEMENT,
                    depends_on=["S2"],
                    success_criteria=[
                        "Requested behavior is implemented.",
                        "No unrelated file churn is introduced.",
                    ],
                    suggested_tools=["edit_file", "read_file"],
                    risk_notes=["Implementation drift from plan can create hidden regressions."],
                    estimated_cost="high",
                ),
                PlanStep(
                    step_id="S4",
                    title="Verify and summarize",
                    description="Run checks, confirm success criteria, and summarize what changed and what remains risky.",
                    kind=StepKind.VERIFY,
                    depends_on=["S3"],
                    success_criteria=[
                        "Verification commands have been run or a clear blocker is reported.",
                        "A concise delivery summary is ready.",
                    ],
                    suggested_tools=["run_checks"],
                    risk_notes=["Unverified changes should never be presented as fully complete."],
                    estimated_cost="medium",
                ),
            ],
        )
