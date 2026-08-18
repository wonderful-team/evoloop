"""
Learning Module Event Subscribers
=================================

Event subscribers for the learning domain.
"""

import logging
from typing import Any

from app.core.engine.rewind import REWIND_REQUESTED, RewindRequestedEvent
from app.core.events.base import BaseEvent
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType
from app.core.execution.macro import MacroMutatedEvent
from app.core.learning.event.schemas import SkillMutatedEvent
from app.core.learning.event.types import SkillEventType
from app.core.learning.skills.sync_service import skill_sync_service
from app.infrastructure.database import session_scope

logger = logging.getLogger(__name__)


@event_register()
class TraceRewindSubscriber:
    """Delete trace events that belong to rewound messages or runs."""

    @event_subscribe(REWIND_REQUESTED)
    async def on_rewind_requested(self, event: RewindRequestedEvent) -> None:
        message_ids = list(event.affected_message_ids or [])
        if event.target_message_id and event.target_message_id not in message_ids:
            message_ids.append(event.target_message_id)

        run_ids = list(event.affected_run_ids or [])

        if not message_ids and not run_ids:
            logger.debug(
                f"[TraceRewindSubscriber] No affected message/run IDs for thread {event.thread_id}; skipping."
            )
            return

        async with session_scope() as session:
            from app.core.learning.trace.repository import trace_repository

            count = await trace_repository.delete_by_thread(
                event.thread_id,
                message_ids=message_ids,
                run_ids=run_ids,
                db=session,
            )

        event.results["trace_events"] = count
        logger.info(
            f"[TraceRewindSubscriber] Deleted {count} trace events for thread {event.thread_id}"
        )


@event_register()
class LearningLifecycleSubscriber:
    """Handle skill lifecycle events without triggering DB→File export loops."""

    @event_subscribe(SystemEventType.SKILL_CREATED)
    async def on_skill_created(self, event: SkillMutatedEvent) -> None:
        """Route-index refresh only; explicit user action exports to SKILL.md."""
        logger.debug(
            "[LearningLifecycleSubscriber] Skill created: %s",
            event.data.get("skill_id"),
        )

    @event_subscribe(SystemEventType.SKILL_UPDATED)
    async def on_skill_updated(self, event: SkillMutatedEvent) -> None:
        """Route-index refresh only; explicit user action exports to SKILL.md."""
        logger.debug(
            "[LearningLifecycleSubscriber] Skill updated: %s",
            event.data.get("skill_id"),
        )

    @event_subscribe(SystemEventType.SKILL_DELETED)
    async def on_skill_deleted(self, event: SkillMutatedEvent) -> None:
        """Remove the physical skill file when the DB row is deleted."""
        data: dict[str, Any] = dict(event.data) if event.data else {}
        skill_id = data.get("skill_id")
        if skill_id is None:
            return

        await skill_sync_service.delete_skill_file(
            skill_id=skill_id,
            namespace=data.get("namespace"),
            name=data.get("name"),
        )


@event_register()
class InitSpecRefreshSubscriber:
    """Refresh the shared L0 RouteCatalog cache when skills or macros mutate.

    Skills that become builtin macros and verified macros both affect the
    voice/chat routing catalog, so we invalidate the in-process spec and ask the
    Huey worker to rebuild the shared cache. The next request loads the
    refreshed catalog.
    """

    @event_subscribe(SystemEventType.SKILL_CREATED)
    @event_subscribe(SystemEventType.SKILL_UPDATED)
    @event_subscribe(SystemEventType.SKILL_DELETED)
    async def on_skill_mutated(self, event: SkillMutatedEvent) -> None:
        await self._schedule_matcher_rebuild(event, "skill", "skill_id")

    @event_subscribe(SystemEventType.MACRO_CREATED)
    @event_subscribe(SystemEventType.MACRO_UPDATED)
    @event_subscribe(SystemEventType.MACRO_DELETED)
    @event_subscribe(SystemEventType.MACRO_OBSOLETED)
    async def on_macro_mutated(self, event: MacroMutatedEvent) -> None:
        await self._schedule_matcher_rebuild(event, "macro", "macro_id")

    async def _schedule_matcher_rebuild(self, event, kind: str, id_key: str) -> None:
        from app.core.routing.matcher_cache import matcher_cache

        await matcher_cache.invalidate_and_schedule_rebuild()
        logger.debug(
            "[InitSpecRefresh] scheduled debounced rebuild after %s event: %s (%s=%s)",
            kind,
            event.event_type,
            id_key,
            event.data.get(id_key) if event.data else None,
        )


@event_register()
class SkillEventSubscriber:
    """Handles skill execution events for skill evolution."""

    @event_subscribe(SkillEventType.SKILL_EXECUTED)
    async def on_skill_executed(self, event: BaseEvent) -> None:
        """
        Log skill execution for monitoring and analytics.

        This handler can be extended for analytics, dashboards, etc.
        """
        skill_name = event.data.get("skill_name")
        thread_id = event.data.get("thread_id")

        logger.debug(f"🎯 Skill executed: {skill_name} in thread {thread_id}")

    @event_subscribe(SkillEventType.SKILL_PROMOTED)
    async def on_skill_promoted(self, event: BaseEvent) -> None:
        """
        Handle skill promotion to built-in status.

        Triggered when a learned skill is promoted to built-in.
        """
        skill_name = event.data.get("skill_name")

        logger.info(f"⭐ Skill promoted to built-in: {skill_name}")

    @event_subscribe(SkillEventType.SKILL_DEPRECATED)
    async def on_skill_deprecated(self, event: BaseEvent) -> None:
        """
        Handle skill deprecation.

        Triggered when a skill is deprecated (replaced or outdated).
        """
        skill_name = event.data.get("skill_name")
        reason = event.data.get("reason", "No reason provided")

        logger.info(f"🗑️ Skill deprecated: {skill_name} - {reason}")
