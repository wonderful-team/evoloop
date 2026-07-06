"""
Vision Event Publishers
=======================

Helper functions for publishing vision processing events.
"""

from app.core.events import system_bus

from .schemas import VisionProcessCompletedEvent, VisionProcessStartedEvent


async def publish_vision_process_started(task: str, source: str) -> None:
    """Publish an event when a vision task starts."""
    await system_bus.publish(
        VisionProcessStartedEvent(data={"task": task, "source": source})
    )


async def publish_vision_process_completed(
    result, task: str, provider_name: str
) -> None:
    """Publish an event when a vision task completes."""
    await system_bus.publish(
        VisionProcessCompletedEvent(
            result=result,
            data={"task": task, "provider": provider_name},
        )
    )
