from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .abstractions import AbstractEvidenceSelector, AbstractTraceProvider
from .domain import DisclosureContext, DisclosureDecision, EvidenceRef
from .events import EventKind


@dataclass(slots=True)
class InlineEvidenceSelector(AbstractEvidenceSelector):
    fallback_sources: Sequence[EvidenceRef] = field(default_factory=tuple)

    def select(self, context: DisclosureContext, decision: DisclosureDecision) -> Sequence[EvidenceRef]:
        if not decision.include_evidence:
            return ()

        results: list[EvidenceRef] = []

        if context.current_action and context.current_action.evidence_refs:
            results.extend(context.current_action.evidence_refs)

        event_kind = getattr(getattr(context, 'event', None), 'kind', None)
        if event_kind in {EventKind.PLAN_CREATED, EventKind.PLAN_UPDATED} and context.plan_outline:
            results.append(
                EvidenceRef(
                    title="Execution plan",
                    source_type="plan",
                    pointer="plan://active",
                    summary="Structured plan exists and can be expanded on demand.",
                )
            )

        if context.state.changed_files:
            results.append(
                EvidenceRef(
                    title="Changed files",
                    source_type="workspace",
                    pointer=", ".join(context.state.changed_files[:5]),
                    summary=f"{len(context.state.changed_files)} file(s) are currently implicated.",
                )
            )

        if context.state.uncertainty_reasons:
            results.append(
                EvidenceRef(
                    title="Uncertainty signals",
                    source_type="analysis",
                    pointer="uncertainty://active",
                    summary="; ".join(context.state.uncertainty_reasons[:3]),
                )
            )

        if len(results) < context.preferences.max_evidence_items:
            for ref in self.fallback_sources:
                if len(results) >= context.preferences.max_evidence_items:
                    break
                results.append(ref)

        return tuple(results[: context.preferences.max_evidence_items])


@dataclass(slots=True)
class StaticTraceProvider(AbstractTraceProvider):
    traces_by_event: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def select(self, context: DisclosureContext, decision: DisclosureDecision) -> Sequence[str]:
        if not decision.include_trace:
            return ()
        key = str(getattr(getattr(context, 'event', None), 'kind', 'default'))
        traces = self.traces_by_event.get(key) or self.traces_by_event.get('default', ())
        return tuple(traces[: context.preferences.max_trace_items])


@dataclass(slots=True)
class StaticPlanProvider:
    outline: Sequence[str]

    def plan_for(self, _task_id: str) -> Sequence[str]:
        return tuple(self.outline)
