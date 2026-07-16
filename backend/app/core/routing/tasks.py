"""Huey tasks that (re)build the VoiceInitSpec.

Runs in the separate Huey worker process and writes the result to the cache
(``voice:init_spec:current``), which ``GET /route/init`` reads on demand. Clients
pull the spec (startup + periodic + reconnect); there is no server-side push
notification (design §6.4.2 / §17).
"""

from __future__ import annotations

import asyncio
import logging

from app.infrastructure.queue.factory import periodic_task, shared_task

logger = logging.getLogger(__name__)

SPEC_CACHE_KEY = "voice:init_spec:current"


async def _rebuild() -> str:
    from app.core.routing.init_spec import build_init_spec, enrich_spec_with_atlas_aliases
    from app.core.routing.sync import rebuild_route_index
    from app.infrastructure.cache import cache

    spec = await asyncio.to_thread(build_init_spec)
    spec = await enrich_spec_with_atlas_aliases(spec)
    try:
        await cache.set(SPEC_CACHE_KEY, spec.model_dump_json())
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.warning("[voice] cache write failed: %s", exc)

    # Populate the route index (local actions + skills + agent) in the same pass.
    try:
        await rebuild_route_index()
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.warning("[voice] route_index rebuild failed (non-critical): %s", exc)

    logger.info(
        "[voice] VoiceInitSpec rebuilt: version=%s actions=%d",
        spec.version,
        len(spec.actions),
    )
    return spec.version


@shared_task(name="build_voice_init_spec")
async def build_voice_init_spec() -> str:
    """Rebuild the Init Spec (clients pull it via GET /route/init)."""
    return await _rebuild()


@periodic_task(cron="0 */6 * * *", name="build_voice_init_spec_periodic")
def build_voice_init_spec_periodic() -> None:
    """Long-period fallback rebuild every 6h (design §19.6).

    Skill create/update/delete trigger an immediate debounced rebuild via
    ``InitSpecRefreshSubscriber``; this periodic task only covers sources that
    have no change events (installed apps, app_usage_rank, ActionRegistry).
    """
    build_voice_init_spec.delay()
