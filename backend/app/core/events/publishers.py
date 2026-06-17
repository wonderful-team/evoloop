"""
Core Event Publishers
=====================

Helper functions for publishing core/system events.

These functions ensure that event publishing is centralized in the core layer,
preventing infrastructure/domain layers from directly accessing the event bus.
"""

from app.core.events import BaseEvent, SystemEventType, system_bus
from app.core.events.schemas import AppStartedEvent, AppStoppingEvent, UserLoggedInEvent, UserLoggedOutEvent


async def publish_app_started(startup_time: float) -> None:
    """Publish the application started event."""
    await system_bus.publish(
        AppStartedEvent(
            source="main",
            data={"startup_time": startup_time},
        )
    )


async def publish_app_stopping() -> None:
    """Publish the application stopping event."""
    await system_bus.publish(
        AppStoppingEvent(
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
            event_type=SystemEventType.EMBEDDING_UPDATED,
            source="embedding_config",
            data={"repo_id": repo_id, "project_id": project_id},
        )
    )


async def publish_user_logged_in(token: str, member_id: int | None = None) -> None:
    """Publish the user logged in event. Subscribers should start user-specific services."""
    await system_bus.publish(
        UserLoggedInEvent(
            source="auth",
            data={"token": token, "member_id": member_id},
        )
    )


async def publish_user_logged_out() -> None:
    """Publish the user logged out event. Subscribers should clean up user-specific services."""
    await system_bus.publish(
        UserLoggedOutEvent(
            source="auth",
            data={},
        )
    )


async def publish_skill_mutated(
    skill_id: int,
    action: str,
    namespace: str | None = None,
    name: str | None = None,
) -> None:
    """Publish a skill lifecycle event (created/updated/deleted)."""
    event_type_map = {
        "create": SystemEventType.SKILL_CREATED,
        "update": SystemEventType.SKILL_UPDATED,
        "delete": SystemEventType.SKILL_DELETED,
    }
    event_type = event_type_map.get(action)
    if not event_type:
        return

    await system_bus.publish(
        BaseEvent(
            event_type=event_type,
            source="learning",
            data={
                "skill_id": skill_id,
                "action": action,
                "namespace": namespace,
                "name": name,
            },
        )
    )
