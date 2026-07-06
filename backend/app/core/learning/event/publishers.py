"""
Learning Event Publishers
=========================

Helper functions for publishing learning-related events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.events import system_bus

if TYPE_CHECKING:
    from app.core.learning.event.schemas import SynthesisCompletedEvent


async def publish_synthesis_completed(
    job_id: int,
    status: str,
    skill_id: int | None = None,
    session_id: str | None = None,
) -> SynthesisCompletedEvent:
    """Publish a public SynthesisCompletedEvent (bridged to frontend SSE)."""
    from app.core.learning.event.schemas import SynthesisCompletedEvent

    event = SynthesisCompletedEvent(
        job_id=job_id,
        status=status,
        skill_id=skill_id,
        session_id=session_id,
    )
    await system_bus.publish(event)
    return event

