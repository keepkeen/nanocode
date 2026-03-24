"""Adaptive progressive disclosure for agentic systems."""

from .domain import (
    ActionKind,
    ActionRecord,
    AgentPhase,
    DisclosureAudience,
    DisclosureContext,
    DisclosureDecision,
    DisclosureLevel,
    DisclosureMessage,
    DisclosurePreferences,
    DisclosureVerbosity,
    EvidenceRef,
    TaskRisk,
    TaskStateSnapshot,
)
from .engine import ProgressiveDisclosureEngine, ProgressiveDisclosureManager
from .events import AgentEvent, EventKind
from .policies import AdaptiveProgressiveDisclosurePolicy
from .providers import InlineEvidenceSelector, StaticPlanProvider, StaticTraceProvider
from .renderers import MarkdownRenderer, StructuredRenderer
from .sinks import InMemorySink, StdoutSink

__all__ = [
    "ActionKind",
    "ActionRecord",
    "AgentEvent",
    "AgentPhase",
    "AdaptiveProgressiveDisclosurePolicy",
    "DisclosureAudience",
    "DisclosureContext",
    "DisclosureDecision",
    "DisclosureLevel",
    "DisclosureMessage",
    "DisclosurePreferences",
    "DisclosureVerbosity",
    "EventKind",
    "EvidenceRef",
    "InMemorySink",
    "InlineEvidenceSelector",
    "MarkdownRenderer",
    "ProgressiveDisclosureEngine",
    "ProgressiveDisclosureManager",
    "StaticPlanProvider",
    "StaticTraceProvider",
    "StdoutSink",
    "StructuredRenderer",
    "TaskRisk",
    "TaskStateSnapshot",
]
