from __future__ import annotations

from dataclasses import dataclass, field

from .abstractions import AbstractDisclosurePolicy, AbstractEventSink, AbstractEvidenceSelector, AbstractRenderer, AbstractTraceProvider
from .domain import DisclosureContext, DisclosureMessage
from .events import AgentEvent
from .novelty import TimeAndNoveltyGate
from .policies import AdaptiveProgressiveDisclosurePolicy
from .providers import InlineEvidenceSelector, StaticTraceProvider
from .renderers import MarkdownRenderer
from .sinks import InMemorySink


@dataclass(slots=True)
class ProgressiveDisclosureEngine:
    policy: AbstractDisclosurePolicy = field(default_factory=AdaptiveProgressiveDisclosurePolicy)
    renderer: AbstractRenderer = field(default_factory=MarkdownRenderer)
    evidence_selector: AbstractEvidenceSelector = field(default_factory=InlineEvidenceSelector)
    trace_provider: AbstractTraceProvider = field(default_factory=StaticTraceProvider)
    novelty_gate: TimeAndNoveltyGate = field(default_factory=TimeAndNoveltyGate)

    def process(self, event: AgentEvent, context: DisclosureContext) -> DisclosureMessage | None:
        enriched = context.with_event(event)
        decision = self.policy.decide(enriched)
        if not decision.should_emit:
            return None
        if not self.novelty_gate.should_emit(enriched, decision):
            return None

        evidence = self.evidence_selector.select(enriched, decision)
        trace = self.trace_provider.select(enriched, decision)
        message = self.renderer.render(enriched, decision, evidence, trace)
        self.novelty_gate.record(enriched, message)
        return message


@dataclass(slots=True)
class ProgressiveDisclosureManager:
    engine: ProgressiveDisclosureEngine = field(default_factory=ProgressiveDisclosureEngine)
    sink: AbstractEventSink = field(default_factory=InMemorySink)

    def handle_event(self, event: AgentEvent, context: DisclosureContext) -> DisclosureMessage | None:
        message = self.engine.process(event, context)
        if message is not None:
            self.sink.publish(message)
        return message
