"""
Macro Execution Event Subscribers
==================================

Event subscribers for macro execution lifecycle.
"""

import logging

from app.core.atlas.source.event.types import AppMapEventType
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import SystemEventType
from app.core.execution.macro import (
    invalidate_macro_cache,
    mark_obsolete_by_app_map,
    synthesize_macros_task,
)
from app.core.execution.macro.event import MacroEventType, MacroExecutionFailedEvent
from app.core.execution.macro.healing_policy import SelfHealingPolicy
from app.core.routing.matcher_cache import matcher_cache
from app.core.routing.navigation_macro_cache import get_navigation_macro_cache

logger = logging.getLogger(__name__)


@event_register()
class MacroAppMapSubscriber:
    """Obsolete macros when their source AppMap is superseded."""

    @event_subscribe("atlas.app_map.superseded")
    async def on_app_map_superseded(self, event) -> None:
        data = event.data or {}
        app_map_id = data.get("app_map_id")
        if not app_map_id:
            return
        await mark_obsolete_by_app_map(int(app_map_id))


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

    @event_subscribe(MacroEventType.EXECUTION_FAILED)
    async def on_macro_failed(self, event: MacroExecutionFailedEvent) -> None:
        """
        Evaluate healing switches and append guidance to the event.
        Uses centralized SelfHealingPolicy for decision making.
        """
        # Use centralized policy check
        decision = SelfHealingPolicy.check(
            macro=None,  # Macro-level check already done in MacroService
            execution_params=event.data,
        )

        if not decision.allowed:
            logger.info(
                "[Self-Healing] %s-level skip for macro failure in thread %s",
                decision.source,
                event.thread_id,
            )
            event.suggestions.append(SelfHealingPolicy.get_disabled_message(decision))
            return

        # Success Case: Suggest recovery with contextual information
        logger.info(
            "[Self-Healing] Suggesting perceptual recovery for macro '%s'",
            event.skill_name,
        )
        event.suggestions.append(
            SelfHealingPolicy.get_enabled_message(
                macro_name=event.skill_name, error_message=event.error_message
            )
        )


@event_register()
class MacroL0MatcherSubscriber:
    """Rebuild L0 local matcher when macros are created/updated/deleted/obsoleted."""

    @staticmethod
    def _macro_id_from_event(event) -> int | None:
        """Extract macro_id from the event payload, tolerating both model and dict forms."""
        macro_id = getattr(event, "macro_id", None)
        if macro_id is not None:
            return macro_id

        data = getattr(event, "data", None)
        if data is None:
            return None

        if isinstance(data, dict):
            return data.get("macro_id")
        return getattr(data, "macro_id", None)

    @event_subscribe(SystemEventType.MACRO_CREATED)
    @event_subscribe(SystemEventType.MACRO_UPDATED)
    @event_subscribe(SystemEventType.MACRO_DELETED)
    @event_subscribe(SystemEventType.MACRO_OBSOLETED)
    async def on_macro_lifecycle(self, event) -> None:
        """Invalidate the L0 RouteCatalog and schedule a debounced rebuild; also
        refresh the navigation macro cache so macro changes are immediately routable.

        Macro lifecycle events can arrive in bursts (e.g. CREATE + multiple UPDATE
        events during synthesis).  A debounced rebuild coalesces the burst into a
        single catalog rebuild after a short delay, while invalidating caches
        eagerly keeps the next API request consistent.
        """
        macro_id = self._macro_id_from_event(event)
        invalidate_macro_cache(macro_id)
        await matcher_cache.invalidate_and_schedule_rebuild()
        try:
            await get_navigation_macro_cache().refresh()
        except Exception:
            logger.warning(
                "[L0Matcher] navigation macro cache refresh failed", exc_info=True
            )

        logger.info(
            "[L0Matcher] scheduled debounced rebuild and navigation cache refresh after macro lifecycle event: %s (macro_id=%s)",
            getattr(event, "event_type", "unknown"),
            macro_id,
        )
