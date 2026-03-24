from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .abstractions import AbstractRenderer
from .domain import DisclosureContext, DisclosureDecision, DisclosureLevel, DisclosureMessage, EvidenceRef
from .events import EventKind


@dataclass(slots=True)
class MarkdownRenderer(AbstractRenderer):
    include_section_headers: bool = True

    def render(
        self,
        context: DisclosureContext,
        decision: DisclosureDecision,
        evidence: Sequence[EvidenceRef],
        trace: Sequence[str],
    ) -> DisclosureMessage:
        sections = self._build_sections(context, decision, evidence, trace)
        summary = self._summary(context, decision)
        body = self._format_sections(sections)
        return DisclosureMessage(
            level=decision.level or DisclosureLevel.ACK,
            title=decision.title or "Agent update",
            summary=summary,
            body=body,
            sections=sections,
            evidence=tuple(evidence),
            trace=tuple(trace),
            require_approval=decision.require_approval,
            metadata={
                "task_id": context.state.task_id,
                "phase": context.phase.value,
                "risk": context.risk.value,
                "event_kind": getattr(getattr(context, "event", None), "kind", None),
                "reasons": tuple(decision.reasons),
            },
        )

    def _summary(self, context: DisclosureContext, decision: DisclosureDecision) -> str:
        step = context.state.current_step or "preparing work"
        if decision.level == DisclosureLevel.ACK:
            return f"已收到任务：{context.state.goal}"
        if decision.level == DisclosureLevel.PLAN:
            return f"正在规划：{step}"
        if decision.level == DisclosureLevel.STEP:
            return f"当前步骤：{step}"
        if decision.level == DisclosureLevel.EVIDENCE:
            return f"当前步骤带有证据/验证信息：{step}"
        return f"提供深度追踪：{step}"

    def _build_sections(
        self,
        context: DisclosureContext,
        decision: DisclosureDecision,
        evidence: Sequence[EvidenceRef],
        trace: Sequence[str],
    ) -> dict[str, Sequence[str] | str]:
        sections: dict[str, Sequence[str] | str] = {}
        for name in decision.sections:
            if name == "mission":
                sections[name] = [f"Goal: {context.state.goal}"]
            elif name == "plan":
                sections[name] = list(context.plan_outline) if context.plan_outline else ["Plan not materialized yet."]
            elif name == "current_action":
                if context.current_action:
                    details = [f"Action: {context.current_action.description}"]
                    if context.current_action.target:
                        details.append(f"Target: {context.current_action.target}")
                    details.append(f"Kind: {context.current_action.kind.value}")
                    sections[name] = details
                else:
                    sections[name] = ["No active action."]
            elif name == "risk":
                risks = [f"Risk: {context.risk.value}", f"Confidence: {context.state.confidence:.2f}"]
                if context.state.uncertainty_reasons:
                    risks.extend([f"Uncertainty: {reason}" for reason in context.state.uncertainty_reasons])
                if context.blocked_reason:
                    risks.append(f"Blocked by: {context.blocked_reason}")
                sections[name] = risks
            elif name == "evidence":
                sections[name] = [f"{ref.title}: {ref.summary} ({ref.pointer})" for ref in evidence] or ["No evidence attached."]
            elif name == "trace":
                sections[name] = list(trace) or ["No trace attached."]
            elif name == "next_step":
                sections[name] = self._next_step_lines(context)
        return sections

    def _next_step_lines(self, context: DisclosureContext) -> list[str]:
        event_kind = getattr(getattr(context, "event", None), "kind", None)
        if event_kind == EventKind.APPROVAL_REQUIRED:
            return ["Awaiting user approval before proceeding."]
        if event_kind == EventKind.ERROR:
            return ["Recover, verify state, and retry safely."]
        if event_kind == EventKind.TASK_COMPLETED:
            return ["Present final outcome and validation evidence."]
        if context.phase.value == "planning":
            return ["Finalize plan and start the first executable sub-step."]
        if context.phase.value == "verification":
            return ["Run validations and summarize evidence."]
        return ["Continue with the next scoped step."]

    def _format_sections(self, sections: dict[str, Sequence[str] | str]) -> str:
        blocks: list[str] = []
        for name, content in sections.items():
            if self.include_section_headers:
                blocks.append(f"## {name.replace('_', ' ').title()}")
            if isinstance(content, str):
                blocks.append(content)
            else:
                blocks.extend(f"- {line}" for line in content)
        return "\n".join(blocks)


@dataclass(slots=True)
class StructuredRenderer(AbstractRenderer):
    def render(
        self,
        context: DisclosureContext,
        decision: DisclosureDecision,
        evidence: Sequence[EvidenceRef],
        trace: Sequence[str],
    ) -> DisclosureMessage:
        return MarkdownRenderer(include_section_headers=False).render(context, decision, evidence, trace)
