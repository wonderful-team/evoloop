"""Init Spec event-triggered refresh (design §19.6).

Rebuild the VoiceInitSpec primarily on skill lifecycle events (created / updated
/ deleted change the ``actions`` list), coalescing bursts into a single rebuild.
ActionRegistry / installed-apps / app_usage_rank have no change events, so a
long-period periodic task (see tasks.py) remains as the fallback. Clients still
PULL via GET /route/init — there is no server-side push (§6.4.2).

Voice terminal result pushback is now handled by ``VoiceChannel``
(``app/core/channel/voice_channel.py``) via the ``UniversalBridgeSubscriber``.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.events import SystemEventType
from app.core.events.decorators import event_register, event_subscribe

logger = logging.getLogger(__name__)
#
# Rebuild the VoiceInitSpec primarily on skill lifecycle events (created / updated
# / deleted change the `actions` list), coalescing bursts into a single rebuild.
# ActionRegistry / installed-apps / app_usage_rank have no change events, so a
# long-period periodic task (see tasks.py) remains as the fallback. Clients still
# PULL via GET /route/init — there is no server-side push (§6.4.2).

_DEBOUNCE_S_DEFAULT = 5.0
_debounce_task: asyncio.Task | None = None
_debounce_lock = asyncio.Lock()
_REBUILD_EXCEPTIONS = (ValueError, OSError, RuntimeError, TypeError, KeyError)


def _debounce_seconds() -> float:
    try:
        from app.infrastructure.config import SystemConfigService

        raw = SystemConfigService.get_value("ROUTE_INIT_SPEC_DEBOUNCE_S")
        if raw is not None:
            return max(0.0, float(raw))
    except _REBUILD_EXCEPTIONS:
        pass
    return _DEBOUNCE_S_DEFAULT


async def _fire_rebuild() -> None:
    try:
        from app.core.routing.tasks import build_voice_init_spec

        build_voice_init_spec.delay()
        logger.info("[voice] Init Spec rebuild enqueued (event-triggered)")
    except _REBUILD_EXCEPTIONS as exc:
        logger.warning("[voice] Init Spec rebuild enqueue failed: %s", exc)


async def schedule_init_spec_rebuild() -> None:
    """Coalesce rapid refresh requests into one rebuild after a debounce window."""
    global _debounce_task
    async with _debounce_lock:
        if _debounce_task is not None and not _debounce_task.done():
            _debounce_task.cancel()
        wait = _debounce_seconds()

        async def _delayed() -> None:
            try:
                await asyncio.sleep(wait)
                await _fire_rebuild()
            except asyncio.CancelledError:
                pass

        _debounce_task = asyncio.create_task(_delayed())


@event_register()
class InitSpecRefreshSubscriber:
    """Rebuild the VoiceInitSpec on skill and macro lifecycle events (debounced). §19.6."""

    @event_subscribe(SystemEventType.SKILL_CREATED)
    async def on_skill_created(self, event) -> None:
        await schedule_init_spec_rebuild()

    @event_subscribe(SystemEventType.SKILL_UPDATED)
    async def on_skill_updated(self, event) -> None:
        await schedule_init_spec_rebuild()

    @event_subscribe(SystemEventType.SKILL_DELETED)
    async def on_skill_deleted(self, event) -> None:
        await schedule_init_spec_rebuild()

    @event_subscribe(SystemEventType.MACRO_CREATED)
    async def on_macro_created(self, event) -> None:
        await schedule_init_spec_rebuild()

    @event_subscribe(SystemEventType.MACRO_UPDATED)
    async def on_macro_updated(self, event) -> None:
        await schedule_init_spec_rebuild()

    @event_subscribe(SystemEventType.MACRO_DELETED)
    async def on_macro_deleted(self, event) -> None:
        await schedule_init_spec_rebuild()

    @event_subscribe(SystemEventType.MACRO_OBSOLETED)
    async def on_macro_obsoleted(self, event) -> None:
        await schedule_init_spec_rebuild()
