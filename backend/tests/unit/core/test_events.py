"""
Unit tests for event system.
"""

import pytest
from unittest.mock import AsyncMock

from app.core.events.base import BaseEvent, AsyncEventBus


class TestBaseEvent:
    """Tests for BaseEvent."""

    def test_create_event(self):
        """Test creating a basic event."""
        event = BaseEvent(
            event_type="test.event",
            source="test",
            data={"key": "value"}
        )

        assert event.event_type == "test.event"
        assert event.source == "test"
        assert event.data == {"key": "value"}
        assert event.timestamp is not None

    def test_type_name_property(self):
        """Test the type_name property."""
        event = BaseEvent(event_type="custom.type")
        assert event.type_name == "custom.type"

        # Without explicit type
        event2 = BaseEvent()
        assert event2.type_name == "BaseEvent"


class TestAsyncEventBus:
    """Tests for AsyncEventBus."""

    @pytest.fixture
    def bus(self):
        """Create a fresh event bus for each test."""
        return AsyncEventBus(name="test-bus")

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, bus):
        """Test subscribing to events and publishing."""
        handler = AsyncMock()

        bus.subscribe("test.event", handler)
        event = BaseEvent(event_type="test.event", data={"test": True})

        await bus.publish(event)

        handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_multiple_handlers(self, bus):
        """Test multiple handlers for same event type."""
        handler1 = AsyncMock()
        handler2 = AsyncMock()

        bus.subscribe("test.event", handler1)
        bus.subscribe("test.event", handler2)

        event = BaseEvent(event_type="test.event")
        await bus.publish(event)

        handler1.assert_called_once()
        handler2.assert_called_once()

    @pytest.mark.asyncio
    async def test_global_handler(self, bus):
        """Test global handlers receive all events."""
        global_handler = AsyncMock()
        specific_handler = AsyncMock()

        bus.subscribe_all(global_handler)
        bus.subscribe("specific.event", specific_handler)

        event1 = BaseEvent(event_type="specific.event")
        event2 = BaseEvent(event_type="other.event")

        await bus.publish(event1)
        await bus.publish(event2)

        # Global handler should receive both
        assert global_handler.call_count == 2
        # Specific handler should receive only one
        specific_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        """Test unsubscribing from events."""
        handler = AsyncMock()

        bus.subscribe("test.event", handler)
        bus.unsubscribe("test.event", handler)

        event = BaseEvent(event_type="test.event")
        await bus.publish(event)

        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_handler_error_isolation(self, bus):
        """Test that one handler's error doesn't affect others."""
        async def failing_handler(event):
            raise ValueError("Handler error")

        good_handler = AsyncMock()

        bus.subscribe("test.event", failing_handler)
        bus.subscribe("test.event", good_handler)

        event = BaseEvent(event_type="test.event")

        # Should not raise
        await bus.publish(event)

        # Good handler should still be called
        good_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_handlers_for_event(self, bus):
        """Test publishing event with no handlers."""
        event = BaseEvent(event_type="unhandled.event")

        # Should not raise
        await bus.publish(event)

    def test_handler_count(self, bus):
        """Test counting handlers for event types."""
        assert bus.handler_count("test.event") == 0

        bus.subscribe("test.event", AsyncMock())
        assert bus.handler_count("test.event") == 1

        bus.subscribe("test.event", AsyncMock())
        assert bus.handler_count("test.event") == 2

    def test_clear(self, bus):
        """Test clearing all handlers."""
        bus.subscribe("test.event", AsyncMock())
        bus.subscribe_all(AsyncMock())

        assert bus.handler_count("test.event") == 1

        bus.clear()

        assert bus.handler_count("test.event") == 0
        assert len(bus._global_handlers) == 0

    @pytest.mark.asyncio
    async def test_enum_event_types(self, bus):
        """Test using enums as event types."""
        from enum import Enum

        class EventTypes(Enum):
            CREATED = "entity.created"
            UPDATED = "entity.updated"

        handler = AsyncMock()
        bus.subscribe(EventTypes.CREATED, handler)

        event = BaseEvent(event_type=EventTypes.CREATED)
        await bus.publish(event)

        handler.assert_called_once()


class TestSystemEventBus:
    """Tests for the singleton SystemEventBus."""

    def test_singleton_instance(self):
        """Test that SystemEventBus is a singleton."""
        from app.core.events.base import SystemEventBus

        bus1 = SystemEventBus()
        bus2 = SystemEventBus()

        assert bus1 is bus2

    @pytest.mark.asyncio
    async def test_global_event_communication(self):
        """Test global event communication across modules."""
        from app.core.events.base import system_bus

        handler = AsyncMock()
        system_bus.subscribe("global.test", handler)

        try:
            event = BaseEvent(event_type="global.test", data={"shared": True})
            await system_bus.publish(event)

            handler.assert_called_once_with(event)
        finally:
            system_bus.unsubscribe("global.test", handler)
