"""
Environment Event Publishers
============================

Centralized event publishing for the environment/awakening domain.
All environment events must be published through these helpers —
no direct system_bus.publish calls outside this module.
"""

from typing import Any

from app.core.events import system_bus
from app.core.events.registry import SystemEventType

from .schemas import (
    AwakenEvent,
    BoundaryLearnedEvent,
    DeviceConnectedEvent,
    DeviceDisconnectedEvent,
    UiTreeObservedEvent,
)


async def publish_awakening_complete(platforms: list[str], project_id: int | None = None) -> None:
    """Publish the awakening complete event."""
    await system_bus.publish(
        AwakenEvent(
            event_type=SystemEventType.AWAKENING_COMPLETE,
            data={"platforms": platforms, "project_id": project_id},
        )
    )


async def publish_boundary_learned(
    tool_name: str,
    category: str,
    description: str,
) -> None:
    """Publish a boundary learned event."""
    await system_bus.publish(
        BoundaryLearnedEvent(
            tool_name=tool_name,
            category=category,
            description=description,
        )
    )


async def publish_device_connected(
    device_id: str,
    device_type: str = "android",
) -> None:
    """Publish a device connected event."""
    await system_bus.publish(
        DeviceConnectedEvent(
            device_id=device_id,
            device_type=device_type,
        )
    )


async def publish_device_disconnected(device_id: str) -> None:
    """Publish a device disconnected event."""
    await system_bus.publish(DeviceDisconnectedEvent(device_id=device_id))


async def publish_ui_tree_observed(
    platform: str,
    bundle_id: str,
    window_title: str,
    elements: list[dict[str, Any]],
    screenshot_hash: str = "",
    version_hash: str = "",
) -> None:
    """Publish a UI tree observed event."""
    event = UiTreeObservedEvent(
        platform=platform,
        bundle_id=bundle_id,
        window_title=window_title,
        elements=elements,
        screenshot_hash=screenshot_hash,
    )
    if version_hash:
        event.data["version_hash"] = version_hash
    await system_bus.publish(event)
