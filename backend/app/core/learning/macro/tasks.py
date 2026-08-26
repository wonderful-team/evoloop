"""Macro background tasks (Huey)."""

from __future__ import annotations

import logging

from app.infrastructure.queue.factory import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="native_macro_maintenance")
async def native_macro_maintenance_task(apps: list[tuple[str, str]] | None = None) -> list[dict]:
    """Resurvey -> regenerate (replace) -> reindex for the configured apps.

    Triggered explicitly (maintenance API / frontend entry) — never
    auto-fired on a schedule (scanning launches apps, which would disturb
    the user; desktop UI macros update on demand instead).
    """
    from app.core.learning.macro.maintenance import native_macro_maintenance

    return await native_macro_maintenance(apps=apps)
