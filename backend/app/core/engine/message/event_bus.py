"""
EventBus — Unified event publishing abstraction.

Provides a single interface for all real-time event publishing,
enabling future migration to persistent message queues (Redis Streams,
RabbitMQ, etc.) without changing caller code.

Current implementation: InMemoryEventBus (wraps SimplePubSubBus)
Future implementations: RedisStreamEventBus, SQLiteEventBus, etc.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from app.utils.pubsub import in_memory_bus

logger = logging.getLogger(__name__)


class EventBus(ABC):
    """Abstract event bus for publishing real-time events."""

    @abstractmethod
    async def publish(self, channel: str, message: Any) -> int:
        """Publish a message to a channel. Returns number of subscribers notified."""
        ...


class InMemoryEventBus(EventBus):
    """
    In-process event bus using SimplePubSubBus.

    Thread-safe for embedded mode. Messages are lost on process restart.
    """

    async def publish(self, channel: str, message: Any) -> int:
        try:
            in_memory_bus.publish(channel, message)
            return 1
        except Exception as e:
            logger.warning(f"[InMemoryEventBus] Publish failed: {e}")
            return 0


# Global singleton instance
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = InMemoryEventBus()
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    """Replace the global event bus (for testing or migration)."""
    global _event_bus
    _event_bus = bus
