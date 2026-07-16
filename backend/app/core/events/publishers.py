"""
Core Event Publishers
=====================

Helper functions for publishing core/system events.

These functions ensure that event publishing is centralized in the core layer,
preventing infrastructure/domain layers from directly accessing the event bus.
"""

from app.core.events import system_bus
from app.core.events.schemas import (
    AppStartedEvent,
    AppStoppingEvent,
    ConfigChangedEvent,
    UserLoggedInEvent,
    UserLoggedOutEvent,
)


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
    from app.core.context.event import ContextPolishingEvent

    await system_bus.publish(
        ContextPolishingEvent(
            source="engine",
            thread_id=thread_id,
            project_id=project_id,
            model=model,
            context=context,
        )
    )


async def publish_session_completed(data) -> None:
    """Publish a session completed event with full SessionCompletedData."""
    from app.core.events.schemas import SessionCompletedEvent

    await system_bus.publish(SessionCompletedEvent(data=data))


async def publish_config_changed(key: str, old_value: str, new_value: str) -> None:
    """Publish a system event when a configuration value changes."""
    await system_bus.publish(
        ConfigChangedEvent(
            source="SystemConfigService",
            key=key,
            old_value=old_value,
            new_value=new_value,
        )
    )


async def publish_embedding_updated(repo_id: int, project_id: int) -> None:
    """Publish a system event when embeddings are updated for a project."""
    from app.infrastructure.embeddings.event import EmbeddingUpdatedEvent

    await system_bus.publish(
        EmbeddingUpdatedEvent(
            source="embedding_config",
            repo_id=repo_id,
            project_id=project_id,
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


async def publish_subscription_changed(member_id: int | None = None, event: str | None = None) -> None:
    """Publish a subscription changed event (bridged to frontend SSE)."""
    from app.core.events.schemas import SubscriptionChangedEvent

    await system_bus.publish(
        SubscriptionChangedEvent(
            source="subscription",
            member_id=member_id,
            event=event,
        )
    )


async def publish_macro_mutated(
    macro_id: int,
    action: str,
    namespace: str | None = None,
    name: str | None = None,
) -> None:
    """Publish a macro lifecycle event (created/updated/deleted/obsoleted).

    Unknown actions are dropped: an event with an empty event_type would be
    unroutable noise on the bus.
    """
    from app.core.execution.macro.event.schemas import MacroMutatedEvent

    if action not in ("create", "update", "delete", "obsolete"):
        return

    await system_bus.publish(
        MacroMutatedEvent(
            source="learning",
            macro_id=macro_id,
            action=action,
            namespace=namespace,
            name=name,
        )
    )


async def publish_skill_mutated(
    skill_id: int,
    action: str,
    namespace: str | None = None,
    name: str | None = None,
) -> None:
    """Publish a skill lifecycle event (created/updated/deleted).

    Unknown actions are dropped: an event with an empty event_type would be
    unroutable noise on the bus.
    """
    from app.core.learning.event import SkillMutatedEvent

    if action not in ("create", "update", "delete"):
        return

    await system_bus.publish(
        SkillMutatedEvent(
            source="learning",
            skill_id=skill_id,
            action=action,
            namespace=namespace,
            name=name,
        )
    )
