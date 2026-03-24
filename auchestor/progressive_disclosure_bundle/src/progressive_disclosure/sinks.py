from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .abstractions import AbstractEventSink
from .domain import DisclosureMessage


@dataclass(slots=True)
class InMemorySink(AbstractEventSink):
    items: list[DisclosureMessage] = field(default_factory=list)

    def publish(self, message: DisclosureMessage) -> None:
        self.items.append(message)


class StdoutSink(AbstractEventSink):
    def publish(self, message: DisclosureMessage) -> None:
        print(f"[{message.level.value.upper()}] {message.title}")
        print(message.summary)
        print(message.body)
        if message.require_approval:
            print("APPROVAL REQUIRED")
        print()
