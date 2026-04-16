"""
Event Bridge Handler
"""
import json
import logging
from app.core.events.base import BaseEvent
from app.core.events.decorators import event_register, event_subscribe_all

logger = logging.getLogger(__name__)


@event_register()
class EventBridgeHandler:
    """
    Subscribes to all events and publishes relevant ones to Redis for frontend.
    """

    # Event types to bridge to frontend
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

    @event_subscribe_all()
    async def on_event(self, event: BaseEvent) -> None:
        """
        Bridge internal events to cache Pub/Sub.
        """
        event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)

        if event_type not in self.BRIDGED_EVENTS:
            return

        frontend_type = self.BRIDGED_EVENTS[event_type]

        try:
            from app.core.monitoring.activity import activity_monitor
            payload = {
                "type": "system_event",
                "event": frontend_type,
                "data": event.data,
                "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp)
            }
            await activity_monitor.client.publish("system:events", json.dumps(payload, ensure_ascii=False))
            logger.debug(f"[EventBridge] Bridged {event_type} -> system:events")
        except Exception as e:
            logger.warning(f"[EventBridge] Failed to bridge event {event_type}: {e}")
