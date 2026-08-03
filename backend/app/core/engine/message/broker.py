"""
MessageBroker — Unified message publishing and subscription abstraction.

Replaces the obsolete EventBus naming to eliminate process-wide event bus confusion.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from redis.exceptions import RedisError

from app.infrastructure.cache.abstract import PubSubBackend
from app.utils.pubsub import in_memory_bus

logger = logging.getLogger(__name__)


class MessageBroker(ABC):
    """Abstract message broker for publishing and subscribing to real-time events/messages."""

    @abstractmethod
    async def publish(self, channel: str, message: Any) -> int:
        """Publish a message to a channel. Returns number of subscribers notified."""
        ...

    @abstractmethod
    def pubsub(self) -> PubSubBackend:
        """Return a PubSub adapter for subscription."""
        ...


class LocalMessageBroker(MessageBroker):
    """
    In-process message broker for single-process deployments (Embedded Mode).
    Uses thread-safe local SimplePubSubBus.
    """

    async def publish(self, channel: str, message: Any) -> int:
        try:
            in_memory_bus.publish(channel, message)
            return 1
        except (RuntimeError, TypeError, AttributeError) as e:
            logger.warning(f"[LocalMessageBroker] Publish failed: {e}")
            return 0

    def pubsub(self) -> PubSubBackend:
        from app.infrastructure.cache.file._pubsub import InMemoryPubSubAdapter

        return InMemoryPubSubAdapter()


class DistributedMessageBroker(MessageBroker):
    """
    Cross-process message broker for distributed deployments (Production Mode).
    Uses a centralized message broker (Redis) via cache infrastructure.
    """

    async def publish(self, channel: str, message: Any) -> int:
        try:
            from app.infrastructure.cache import cache

            return await cache.publish(channel, message)
        except (RedisError, OSError, TypeError, ValueError) as e:
            logger.error(f"[DistributedMessageBroker] Publish failed to channel {channel}: {e}")
            return 0

    def pubsub(self) -> PubSubBackend:
        from app.infrastructure.cache import cache

        return cache.pubsub()


# Global singleton instance
_message_broker: MessageBroker | None = None


def get_message_broker() -> MessageBroker:
    """
    Get the global message broker instance.

    Selects implementation based on settings.EMBEDDED_MODE.
    """
    global _message_broker
    if _message_broker is None:
        from app.core.config import settings

        if settings.EMBEDDED_MODE:
            logger.info("[MessageBroker] Initializing LocalMessageBroker (Embedded Mode)")
            _message_broker = LocalMessageBroker()
        else:
            logger.info("[MessageBroker] Initializing DistributedMessageBroker (Production Mode)")
            _message_broker = DistributedMessageBroker()

    return _message_broker
