"""ThreadGate — session event gate (channel-agnostic hang/wake primitive).

The session main loop parks on ``wait_next()`` when it has no work;
external entrypoints (voice_ws / _chat / mobile subscribers / A2A 回调 /
HITL 恢复) inject events via ``put()`` to wake it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class GateEvent:
    """A single event consumed by the session main loop."""

    kind: Literal[
        "user_message",
        "session_cancel",
        "session_close",
    ]
    payload: dict[str, Any] = field(default_factory=dict)


class ThreadGate:
    """Asyncio queue that parks the session loop and wakes it on injection."""

    def __init__(self) -> None:
        self._events: asyncio.Queue[GateEvent] = asyncio.Queue()

    async def wait_next(self) -> GateEvent:
        """Park the session main loop (no LLM/CPU consumed while parked)."""
        return await self._events.get()

    def put(self, ev: GateEvent) -> None:
        """Inject an event (called from voice_ws / _chat / subscribers / callbacks)."""
        self._events.put_nowait(ev)

    def drain(self) -> list[GateEvent]:
        """Non-blocking drain of all currently queued events (for tests/teardown)."""
        events: list[GateEvent] = []
        while not self._events.empty():
            events.append(self._events.get_nowait())
        return events
