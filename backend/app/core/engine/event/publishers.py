"""
Agent Engine Event Publishers
=============================

Helper functions for publishing agent-related events.
"""

from app.core.events import system_bus

from .schemas import AgentRunCompletedEvent, WebSocketMessageReceivedEvent


async def publish_agent_run_completed(
    thread_id: str,
    project_id: int = 1,
    goal: str = "",
    status: str = "done",
    payload: dict | None = None,
) -> None:
    """Publish an event when an agent run completes."""
    event_payload = payload or {}
    await system_bus.publish(
        AgentRunCompletedEvent(
            thread_id=thread_id,
            project_id=project_id,
            goal=goal,
            status=status,
            payload=event_payload,
        )
    )


async def publish_ws_message_received(
    msg_type: str,
    payload: dict,
    raw: dict,
) -> None:
    """Publish a generic WebSocket message received event."""
    await system_bus.publish(
        WebSocketMessageReceivedEvent(
            msg_type=msg_type or "unknown",
            payload=payload,
            raw=raw,
        )
    )
