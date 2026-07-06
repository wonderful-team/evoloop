"""
Engine Event Handlers
=====================

Command handler modules for the engine event subscriber.

These handlers are instantiated by ``EngineCommandSubscriber`` and are not
auto-registered with the event bus. They encapsulate grouped command logic
(memory, A2A) that would otherwise bloat the main subscriber class.
"""

from .a2a import A2ACommandHandler
from .memory import MemoryCommandHandler

__all__ = [
    "MemoryCommandHandler",
    "A2ACommandHandler",
]
