"""
Macro Execution Event Subscribers
==================================

Event subscribers for macro execution lifecycle.
"""

import logging

from app.core.atlas.source.event.types import AppMapEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType
from app.core.events.schemas.lifecycle import SessionCompletedEvent
from app.core.execution.macro.event import MacroEventType, MacroExecutionFailedEvent
from app.core.execution.macro.healing_policy import SelfHealingPolicy

logger = logging.getLogger(__name__)


@event_register()
class MacroSedimentationSubscriber:
    """Create a pending_review macro from a completed, eligible trace."""

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: SessionCompletedEvent) -> None:
        if not getattr(event.data, "sedimentation_eligible", False):
            return

        thread_id = event.data.thread_id
        member_id = getattr(event.data, "member_id", None) or 0
        from app.core.execution.macro.sedimentation_service import (
            MacroSedimentationService,
        )

        await MacroSedimentationService.sediment(thread_id, member_id=member_id)


@event_register()
class MacroAppMapSubscriber:
    """Obsolete macros when their source AppMap is superseded."""

    @event_subscribe("atlas.app_map.superseded")
    async def on_app_map_superseded(self, event) -> None:
        data = event.data or {}
        app_map_id = data.get("app_map_id")
        if not app_map_id:
            return
        from app.core.execution.macro import lifecycle

        await lifecycle.mark_obsolete_by_app_map(int(app_map_id))


@event_register()
class MacroAppMapGenerateCompletedSubscriber:
    """Schedule macro synthesis when an AppMap is marked complete."""

    @event_subscribe(AppMapEventType.GENERATE_COMPLETED)
    async def on_app_map_generate_completed(self, event) -> None:
        data = event.data or {}
        app_map_id = data.get("app_map_id")
        project_id = data.get("project_id")
        member_id = data.get("member_id") or 0
        if not app_map_id or not project_id:
            logger.warning(
                "[Macro] generate_completed event missing app_map_id/project_id"
            )
            return

        from app.core.execution.macro.tasks import synthesize_macros_task

        synthesize_macros_task.delay(
            app_map_id=int(app_map_id),
            project_id=int(project_id),
            member_id=int(member_id),
        )
        logger.info(
            "[Macro] Dispatched synthesis for AppMap %s (project %s)",
            app_map_id,
            project_id,
        )


@event_register()
class MacroSelfHealingAdvisor:
    """
    Decoupled listener that decides if an agent should attempt self-healing
    after a macro fails.

    This advisor uses the centralized SelfHealingPolicy for consistency,
    but adds contextual suggestions based on the failure context.
    """

    def __init__(self):
        pass

    @event_subscribe(MacroEventType.EXECUTION_FAILED)
    async def on_macro_failed(self, event: MacroExecutionFailedEvent) -> None:
        """
        Evaluate healing switches and append guidance to the event.
        Uses centralized SelfHealingPolicy for decision making.
        """
        # Use centralized policy check
        decision = SelfHealingPolicy.check(
            skill=None,  # Skill-level check already done in MacroService
            execution_params=event.data,
        )

        if not decision.allowed:
            logger.info(f"[Self-Healing] {decision.source}-level skip for macro failure in thread {event.thread_id}")
            event.suggestions.append(SelfHealingPolicy.get_disabled_message(decision))
            return

        # Success Case: Suggest recovery with contextual information
        logger.info(f"[Self-Healing] Suggesting perceptual recovery for macro '{event.skill_name}'")
        event.suggestions.append(
            SelfHealingPolicy.get_enabled_message(
                skill_name=event.skill_name,
                error_message=event.error_message
            )
        )
