"""Idempotency helper for voice route requests (message_id dedupe).

The voice channel is deployed single-process (``workers=None``), so an
in-process ``dict`` guarded by ``_LOCK`` gives strict, cache-backend-independent
dedupe — this avoids the embedded FileCache's get/set semantics (no TTL, and
not guaranteed to be visible across reads) which previously let a replayed
``message_id`` slip through. The goal is to avoid double-executing a route that
is re-sent after a WebSocket reconnect or a quick client retry. If the channel
ever goes multi-worker, swap this for an atomic cache ``SET NX EX``.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.infrastructure.config import SystemConfigService

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 300
_LOCK = asyncio.Lock()
# message_id -> monotonic expiry timestamp
_seen: dict[str, float] = {}
_PURGE_THRESHOLD = 1024


async def _ttl_seconds() -> int:
    """Read `ROUTE_IDEMPOTENCY_TTL` (seconds), falling back to the default."""
    try:
        raw = await asyncio.to_thread(
            SystemConfigService.get_value, "ROUTE_IDEMPOTENCY_TTL"
        )
        if raw is not None:
            return max(1, int(raw))
    except Exception:
        logger.debug(
            "[idempotency] failed to read ROUTE_IDEMPOTENCY_TTL", exc_info=True
        )
    return _DEFAULT_TTL


async def is_duplicate(message_id: str, ttl: int | None = None) -> bool:
    """Return True if `message_id` was already seen within the dedupe window.

    On first sight the id is recorded (with an expiry) and the function returns
    False. Dedupe is in-process only; see module docstring for the rationale.
    """
    if not message_id:
        return False
    if ttl is None:
        ttl = await _ttl_seconds()
    now = time.monotonic()
    async with _LOCK:
        if len(_seen) > _PURGE_THRESHOLD:
            for k in [k for k, exp in _seen.items() if exp <= now]:
                _seen.pop(k, None)
        exp = _seen.get(message_id)
        if exp is not None and exp > now:
            return True
        _seen[message_id] = now + ttl
        return False
