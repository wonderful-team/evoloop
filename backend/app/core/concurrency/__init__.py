"""
Concurrency primitives for session-level serialization and cancellation.

- SessionSerialQueue: per-thread FIFO queue ensuring same-session requests
  are processed serially (no concurrent execution within a session).
- CancelRegistry: central registry of active runs with zero-latency
  cancellation via asyncio.Event + asyncio.Task.cancel().
"""

from .cancel_registry import CancelRegistry, cancel_registry
from .session_queue import SessionSerialQueue, SessionSlot

__all__ = [
    "SessionSerialQueue",
    "SessionSlot",
    "CancelRegistry",
    "cancel_registry",
]
