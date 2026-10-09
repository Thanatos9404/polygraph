"""Event stream shared by the CLI, the API server, and recorded runs."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

STAGES = [
    ("ingest", "Ingest"),
    ("claims", "Claim ledger"),
    ("research", "Research"),
    ("plan", "Experiment plan"),
    ("probes", "Probe synthesis"),
    ("calibrate", "Calibration"),
    ("execute", "Twin execution"),
    ("compare", "Divergence mining"),
    ("verdict", "Verdict"),
]


@dataclass
class Event:
    type: str
    data: dict[str, Any]
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "ts": round(self.ts, 3), "data": self.data}


Sink = Callable[[Event], Awaitable[None] | None]


class EventBus:
    """Fans events out to any number of sinks and keeps the full history for replay."""

    def __init__(self) -> None:
        self.history: list[Event] = []
        self._sinks: list[Sink] = []
        self._queues: list[asyncio.Queue[Event | None]] = []
        self.closed = False

    def add_sink(self, sink: Sink) -> None:
        self._sinks.append(sink)

    def subscribe(self) -> asyncio.Queue[Event | None]:
        q: asyncio.Queue[Event | None] = asyncio.Queue()
        for ev in self.history:
            q.put_nowait(ev)
        if self.closed:
            q.put_nowait(None)
        else:
            self._queues.append(q)
        return q

    async def emit(self, type: str, **data: Any) -> Event:
        ev = Event(type=type, data=data)
        self.history.append(ev)
        for sink in self._sinks:
            res = sink(ev)
            if asyncio.iscoroutine(res):
                await res
        for q in self._queues:
            q.put_nowait(ev)
        return ev

    def close(self) -> None:
        self.closed = True
        for q in self._queues:
            q.put_nowait(None)
        self._queues.clear()
