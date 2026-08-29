"""HTTP endpoints for the voice channel: Init Spec bulk fetch + diagnostics.

Loopback-only (defence in depth on top of the loopback binding). The bulk Init
Spec travels over HTTP (cacheable, large, rare); clients pull it on startup,
periodically, and on reconnect. The WebSocket carries only the hot path.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.core.routing.constants import SPEC_CACHE_KEY
from app.core.routing.deps import require_loopback

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/init", dependencies=[Depends(require_loopback)])
async def route_init(version: str = Query(""), platform: str = Query("macos")):
    """Return the current Init Spec, or `{unchanged: true}` if version matches."""
    from app.infrastructure.cache import cache

    logger.debug("[route] /route/init platform=%s version=%s", platform, version)
    raw = None
    try:
        raw = await cache.get(SPEC_CACHE_KEY)
    except Exception as exc:
        logger.warning("[route] cache read failed: %s", exc)

    if not raw:
        return JSONResponse(status_code=202, content={"version": "pending", "unchanged": False})

    try:
        spec = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError) as exc:
        logger.warning("[route] bad cached spec: %s", exc)
        return JSONResponse(status_code=202, content={"version": "pending", "unchanged": False})

    current = spec.get("version", "")
    if version and version == current:
        return {"version": current, "unchanged": True}
    return {**spec, "unchanged": False}
