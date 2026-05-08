"""
Core Event Publishers
=====================

Helper functions for publishing core/system events.

These functions ensure that event publishing is centralized in the core layer,
preventing infrastructure/domain layers from directly accessing the event bus.
"""

from app.core.events import BaseEvent, SystemEventType, system_bus


async def publish_app_started(startup_time: float) -> None:
    """Publish the application started event."""
    await system_bus.publish(
        BaseEvent(
            event_type=SystemEventType.APP_STARTED,
            source="main",
            data={"startup_time": startup_time},
        )
    )


async def publish_app_stopping() -> None:
    """Publish the application stopping event."""
    await system_bus.publish(
        BaseEvent(
            event_type=SystemEventType.APP_STOPPING,
            source="main",
            data={},
        )
    )


async def publish_context_polishing(thread_id: str, project_id: int | None, model: str, context: dict) -> None:
    """Publish a context polishing event."""
    await system_bus.publish(
        BaseEvent(
            event_type=SystemEventType.CONTEXT_POLISHING,
            source="engine",
            data={
                "thread_id": thread_id,
                "project_id": project_id,
                "model": model,
                "context": context,
            },
        )
    )


async def publish_session_completed(data) -> None:
    """Publish a session completed event with full SessionCompletedData."""
    from app.core.events.schemas import SessionCompletedEvent

    await system_bus.publish(SessionCompletedEvent(data=data))


async def publish_config_changed(key: str, old_value: str, new_value: str) -> None:
    """Publish a system event when a configuration value changes."""
    await system_bus.publish(
        BaseEvent(
            event_type=SystemEventType.CONFIG_CHANGED,
            source="SystemConfigService",
            data={
                "key": key,
                "old_value": old_value,
                "new_value": new_value,
            },
        )
    )


async def publish_embedding_updated(repo_id: int, project_id: int) -> None:
    """Publish a system event when embeddings are updated for a project."""
    await system_bus.publish(
        BaseEvent(
            event_type="system.embedding_updated",
            source="embedding_config",
            data={"repo_id": repo_id, "project_id": project_id},
        )
    )


async def publish_user_logged_in(token: str, member_id: int | None = None) -> None:
    """Publish the user logged in event. Subscribers should start user-specific services."""
    await system_bus.publish(
        BaseEvent(
            event_type=SystemEventType.USER_LOGGED_IN,
            source="auth",
            data={"token": token, "member_id": member_id},
        )
    )


async def publish_user_logged_out() -> None:
    """Publish the user logged out event. Subscribers should clean up user-specific services."""
    await system_bus.publish(
        BaseEvent(
            event_type=SystemEventType.USER_LOGGED_OUT,
            source="auth",
            data={},
        )
    )
