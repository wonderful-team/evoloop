"""
Agent Engine Event Publishers
=============================

Helper functions for publishing agent-related events.
"""

from app.constants import DEFAULT_PROJECT_ID
from app.core.events import system_bus
from app.core.monitoring.constants import ActivityStatus

from .schemas import (
    AgentRunCompletedEvent,
    AgentSessionStartedEvent,
    ConversationCreatedEvent,
    ConversationDeletedEvent,
    ConversationUpdatedEvent,
    WebSocketMessageReceivedEvent,
)


async def publish_agent_session_started(
    thread_id: str,
    project_id: int | None = None,
) -> None:
    """Publish an event to request context hydration at the start of a session."""
    await system_bus.publish(
        AgentSessionStartedEvent(
            thread_id=thread_id,
            project_id=project_id,
        )
    )


async def publish_agent_run_completed(
    thread_id: str,
    project_id: int = DEFAULT_PROJECT_ID,
    goal: str = "",
    status: ActivityStatus = ActivityStatus.DONE,
    source: str = "",
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
            source=source,
            payload=event_payload,
        )
    )


async def publish_conversation_deleted(thread_id: str) -> None:
    """Publish a conversation deletion event for domain subscribers."""
    await system_bus.publish(ConversationDeletedEvent(thread_id=thread_id))


async def publish_conversation_created(
    thread_id: str,
    project_id: int = DEFAULT_PROJECT_ID,
    member_id: int = 0,
    title: str = "",
) -> None:
    """Publish a conversation-created event so frontends can refresh their lists."""
    await system_bus.publish(
        ConversationCreatedEvent(
            thread_id=thread_id,
            project_id=project_id,
            member_id=member_id,
            title=title,
        )
    )


async def publish_conversation_updated(
    thread_id: str,
    project_id: int = DEFAULT_PROJECT_ID,
    member_id: int = 0,
    title: str = "",
    status: str = "",
) -> None:
    """Publish a conversation-updated event so frontends can refresh their lists."""
    await system_bus.publish(
        ConversationUpdatedEvent(
            thread_id=thread_id,
            project_id=project_id,
            member_id=member_id,
            title=title,
            status=status,
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
            msg_type=msg_type,
            payload=payload,
            raw=raw,
        )
    )
