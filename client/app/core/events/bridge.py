"""
Event Bridge Handler

Bridges internal system events to Sidecar protocol for frontend streaming.
Enables real-time UI updates when system state changes occur.
"""

import json
import logging

from app.core.events.base import BaseEvent
from app.sidecar.handlers.events import events as sidecar_events

logger = logging.getLogger(__name__)


class EventBridgeHandler:
    """
    Subscribes to key internal events and publishes them via Sidecar protocol.

    This enables the frontend (via Tauri) to receive real-time updates about:
    - Device connections/disconnections
    - Skill promotions/deprecations
    - Project switching
    - System state changes
    """

    # Event types to bridge to frontend
    # Maps internal event type -> frontend event type name
    BRIDGED_EVENTS = {
        "device.connected": "device_connected",
        "device.disconnected": "device_disconnected",
        "skill.promoted": "skill_promoted",
        "skill.deprecated": "skill_deprecated",
        "skill.executed": "skill_executed",
        "project.created": "project_created",
        "project.switched": "project_switched",
        "system.awakening_complete": "awakening_complete",
        "system.boundary_learned": "boundary_learned",
    }

    @staticmethod
    async def on_event(event: BaseEvent) -> None:
        """
        Bridge internal events to Sidecar protocol.

        Publishes to Tauri via Sidecar stdout protocol.
        """
        event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)

        # Only bridge configured events
        if event_type not in EventBridgeHandler.BRIDGED_EVENTS:
            return

        frontend_type = EventBridgeHandler.BRIDGED_EVENTS[event_type]

        try:
            # Create frontend-friendly payload
            payload = {
                "type": "system_event",
                "event": frontend_type,
                "data": event.data,
                "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp)
            }

            # Send via Sidecar protocol instead of Redis
            await sidecar_events._send("system_event", payload)

            logger.debug(f"[EventBridge] Bridged {event_type} -> sidecar")

        except Exception as e:
            logger.warning(f"[EventBridge] Failed to bridge event {event_type}: {e}")


def register_event_bridge() -> None:
    """
    Register the event bridge with both event buses.

    Subscribes to the system bus and awakening bus to capture all relevant events.
    """
    from app.core.environment.events import event_bus as awaken_bus
    from app.core.events import system_bus

    # Subscribe to system bus (for project events)
    system_bus.subscribe_all(EventBridgeHandler.on_event)

    # Subscribe to awakening bus (for device/skill events)
    awaken_bus.subscribe_all(EventBridgeHandler.on_event)

    logger.info("📡 Event bridge registered (Internal → Sidecar)")
