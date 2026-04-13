"""
Core Event System - Base Classes

This module defines the foundational event bus infrastructure for the entire system.
All domain-specific event buses should inherit from AsyncEventBus.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

from app.utils.async_utils import LoopBoundResource
from app.utils.model_helpers import LegacyDictMixin

logger = logging.getLogger(__name__)


# Type variable for event types
E = TypeVar("E", bound="BaseEvent")


class EventData(BaseModel, LegacyDictMixin):
    """Dynamic payload for system events."""
    model_config = ConfigDict(extra="allow")


class BaseEvent(BaseModel, LegacyDictMixin):
    """
    Base class for all system events.
    """
    event_type: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    source: str = "system"
    data: EventData = Field(default_factory=EventData)

    @property
    def type_name(self) -> str:
        """Human-readable event type name."""
        return self.event_type or self.__class__.__name__

    def model_post_init(self, __context: Any) -> None:
        """Ensure event_type is set if not provided."""
        if not self.event_type:
            self.event_type = self.__class__.__name__


# Type alias for event handlers
EventHandler = Callable[[BaseEvent], Awaitable[None]]


class AsyncEventBus(Generic[E]):
    """
    Generic asynchronous event bus implementing publish-subscribe pattern.
    
    This is the core infrastructure for decoupled event-driven communication.
    All handlers are async and executed concurrently using asyncio.gather.
    
    Features:
    - Type-safe event subscription
    - Concurrent async handler execution
    - Error isolation between handlers
    - Global handlers for cross-cutting concerns (logging, auditing)
    
    Usage:
        bus = AsyncEventBus()
        bus.subscribe("user.created", my_handler)
        await bus.publish(UserCreatedEvent(...))
    """

    def __init__(self, name: str = "default"):
        self._name = name
        self._handlers: dict[str, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []
        self._initialized = False
        self._lock_pool = LoopBoundResource(asyncio.Lock)

    @property
    def name(self) -> str:
        return self._name

    def subscribe(self, event_type: str | Enum, handler: EventHandler) -> None:
        """
        Subscribe a handler to a specific event type.
        
        Args:
            event_type: The event type to subscribe to (string or Enum)
            handler: Async function that will be called when event is published
        """
        type_key = event_type.value if isinstance(event_type, Enum) else event_type

        if type_key not in self._handlers:
            self._handlers[type_key] = []

        if handler not in self._handlers[type_key]:
            self._handlers[type_key].append(handler)
            logger.debug(f"[{self._name}] Subscribed handler to {type_key}")

    def subscribe_all(self, handler: EventHandler) -> None:
        """
        Subscribe a handler to all events (for logging/monitoring).
        
        Global handlers receive every published event regardless of type.
        """
        if handler not in self._global_handlers:
            self._global_handlers.append(handler)
            logger.debug(f"[{self._name}] Subscribed global handler")

    def unsubscribe(self, event_type: str | Enum, handler: EventHandler) -> None:
        """Unsubscribe a handler from an event type."""
        type_key = event_type.value if isinstance(event_type, Enum) else event_type

        if type_key in self._handlers and handler in self._handlers[type_key]:
            self._handlers[type_key].remove(handler)
            logger.debug(f"[{self._name}] Unsubscribed handler from {type_key}")

    async def publish(self, event: E) -> None:
        """
        Publish an event to all subscribed handlers.
        
        Handlers are executed concurrently using asyncio.gather.
        Errors in individual handlers don't affect others.
        
        Args:
            event: The event instance to publish
        """
        type_key = event.event_type.value if isinstance(event.event_type, Enum) else event.event_type

        handlers = self._handlers.get(type_key, []) + self._global_handlers

        if not handlers:
            logger.debug(f"[{self._name}] No handlers for event: {type_key}")
            return

        logger.info(f"[{self._name}] 📡 Publishing event: {type_key}")

        async def safe_handle(handler: EventHandler) -> None:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"[{self._name}] Handler failed for {type_key}: {e}")

        await asyncio.gather(*[safe_handle(h) for h in handlers])

    def handler_count(self, event_type: str | Enum) -> int:
        """Get the number of handlers for an event type."""
        type_key = event_type.value if isinstance(event_type, Enum) else event_type
        return len(self._handlers.get(type_key, []))

    def clear(self) -> None:
        """Clear all handlers (for testing)."""
        self._handlers.clear()
        self._global_handlers.clear()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def mark_initialized(self) -> None:
        self._initialized = True


# ============================================================
# Singleton System Bus
# ============================================================

class SystemEventBus(AsyncEventBus):
    """
    Singleton system-wide event bus.
    
    Use this for cross-domain events that need to be accessible globally.
    Domain-specific buses (like AwakenEventBus) can bridge to this bus.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.__init__("system")
        return cls._instance


# Global instance
system_bus = SystemEventBus()
