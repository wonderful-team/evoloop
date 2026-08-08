"""Fetch current environment context for context-aware intent routing."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def resolve_context() -> dict[str, Any]:
    """Fetch current environment context: active app, phone connection."""
    try:
        from app.core.environment import get_current_app_context

        app_info = await asyncio.to_thread(get_current_app_context)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[context_probe] get_current_app failed: %s", exc)
        app_info = None
    active_app = app_info.name if app_info else ""

    try:
        from app.core.environment.state import get_awakened_state

        state = get_awakened_state()
        phone_connected = (
            any(d.is_reachable for d in (state.android_devices or []))
            if state
            else False
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[context_probe] get_awakened_state failed: %s", exc)
        phone_connected = False

    return {"app": active_app, "phone_connected": phone_connected}


__all__ = ["resolve_context"]
