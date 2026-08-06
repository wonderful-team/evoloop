"""Huey tasks that (re)build the Layer-0 RouteCatalog.

Runs in the separate Huey worker process and writes the result to the cache
(``voice:init_spec:current``), which ``GET /route/init`` reads on demand. Clients
pull the spec (startup + periodic + reconnect); there is no server-side push
notification (design §6.4.2 / §17).
"""

from __future__ import annotations

import logging

from app.infrastructure.queue.factory import periodic_task, shared_task

logger = logging.getLogger(__name__)


async def _rebuild() -> str:
    from app.core.routing.matcher_cache import build_and_cache_spec

    spec = await build_and_cache_spec()
    logger.info(
        "[voice] RouteCatalog rebuilt: version=%s actions=%d",
        spec.version,
        len(spec.actions),
    )
    return spec.version


@shared_task(name="build_l0_init_spec")
async def build_l0_init_spec() -> str:
    """Rebuild the Init Spec (clients pull it via GET /route/init)."""
    return await _rebuild()


@periodic_task(cron="0 */6 * * *", name="build_l0_init_spec_periodic")
def build_l0_init_spec_periodic() -> None:
    """Long-period fallback rebuild every 6h (design §19.6).

    Skill create/update/delete trigger an immediate debounced rebuild via
    ``InitSpecRefreshSubscriber``; this periodic task only covers sources that
    have no change events (installed apps, app_usage_rank, ActionRegistry).
    """
    build_l0_init_spec.delay()
