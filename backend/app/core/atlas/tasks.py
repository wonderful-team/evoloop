"""Huey schedule for Atlas-Native maintenance (see maintenance.py docstring)."""

from __future__ import annotations

import logging

from app.core.atlas.maintenance import native_atlas_maintenance
from app.infrastructure.queue.factory import periodic_task, shared_task

logger = logging.getLogger(__name__)


@shared_task(name="native_atlas_maintenance")
async def native_atlas_maintenance_task() -> list[dict]:
    """Resurvey -> regenerate (replace) -> reindex for the configured apps."""
    return await native_atlas_maintenance()


@periodic_task(cron="23 */12 * * *", name="native_atlas_maintenance_periodic")
def native_atlas_maintenance_periodic() -> None:
    """Every 12h, offset from the 6h init-spec rebuild."""
    native_atlas_maintenance_task.delay()
