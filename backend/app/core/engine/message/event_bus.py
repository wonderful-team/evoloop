"""
EventBus — Unified event publishing abstraction.

Provides a single interface for all real-time event publishing,
enabling future migration to persistent message queues (e.g. Redis Streams,
RabbitMQ, etc.) without changing caller code.

Current implementation: InMemoryEventBus (wraps SimplePubSubBus)
Future implementations: RedisStreamEventBus, SQLiteEventBus, etc. (production only)
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from redis.exceptions import RedisError

from app.utils.pubsub import in_memory_bus

logger = logging.getLogger(__name__)


class EventBus(ABC):
    """Abstract event bus for publishing real-time events."""

    @abstractmethod
    async def publish(self, channel: str, message: Any) -> int:
        """Publish a message to a channel. Returns number of subscribers notified."""
        ...


class LocalEventBus(EventBus):
    """
    In-process event bus for single-process deployments (Embedded Mode).
    Fast and requires no external dependencies, but messages are not 
    shared across different processes.
    """

    async def publish(self, channel: str, message: Any) -> int:
        try:
            in_memory_bus.publish(channel, message)
            return 1
        except (RuntimeError, TypeError, AttributeError) as e:
            logger.warning(f"[LocalEventBus] Publish failed: {e}")
            return 0


class DistributedEventBus(EventBus):
    """
    Cross-process event bus for distributed deployments (Production Mode).
    Uses a centralized message broker to sync events 
    across API servers, workers, and background agents.
    """

    async def publish(self, channel: str, message: Any) -> int:
        try:
            # Use the configured cache infrastructure as the message broker
            from app.infrastructure.cache import cache
            return await cache.publish(channel, message)
        except (RedisError, OSError, TypeError, ValueError) as e:
            logger.error(f"[DistributedEventBus] Publish failed to channel {channel}: {e}")
            return 0


# Global singleton instance
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """
    Get the global event bus instance.
    
    Selects implementation based on the system's operating mode:
    - EMBEDDED_MODE=true  -> LocalEventBus (Standalone/Desktop)
    - EMBEDDED_MODE=false -> DistributedEventBus (Cloud/Production)
    """
    global _event_bus
    if _event_bus is None:
        from app.core.config import settings
        
        if settings.EMBEDDED_MODE:
            logger.info("[EventBus] Initializing LocalEventBus (Embedded Mode)")
            _event_bus = LocalEventBus()
        else:
            logger.info("[EventBus] Initializing DistributedEventBus (Production Mode)")
            _event_bus = DistributedEventBus()
            
    return _event_bus


def set_event_bus(bus: EventBus) -> None:
    """Replace the global event bus (for testing or migration)."""
    global _event_bus
    _event_bus = bus
