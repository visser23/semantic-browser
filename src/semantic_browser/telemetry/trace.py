"""Step-level in-memory tracing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _utc_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass
class TraceStore:
    events: list[dict[str, Any]] = field(default_factory=list)
    max_events: int = 1000

    def add(self, kind: str, payload: dict[str, Any]) -> None:
        self.events.append({"ts": _utc_iso(), "kind": kind, "payload": payload})
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]
