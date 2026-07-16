"""In-process registry of voice WebSocket connections.

Maps a voice `thread_id` to the live connection that should receive the
matching `voice.route_result`. The Init Spec is delivered via client pull
(``GET /route/init``); there is no server-side push/bridging (design §6.4.2).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


# Terminal voice.route_result bodies keyed by message_id. Allows duplicate route
# requests to be answered with the final result once the original execution has
# finished. TTL matches the idempotency window (5 minutes default).
_TERMINAL_RESULT_TTL = 300
_TERMINAL_RESULTS: dict[str, tuple[float, dict[str, Any]]] = {}
_TERMINAL_RESULTS_LOCK = asyncio.Lock()


class VoiceConnectionManager:
    def __init__(self) -> None:
        self._conns: dict[str, WebSocket] = {}
        self._thread_to_conn: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # -- connection lifecycle -------------------------------------------

    async def register(self, conn_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._conns[conn_id] = ws

    async def unregister(self, conn_id: str) -> None:
        from app.core.routing import session_frame

        async with self._lock:
            self._conns.pop(conn_id, None)
            stale = [tid for tid, cid in self._thread_to_conn.items() if cid == conn_id]
            for tid in stale:
                self._thread_to_conn.pop(tid, None)
        # Conversation over -> session frames die with it (multi-turn is
        # only supported inside a continuous conversation).
        for tid in stale:
            session_frame.clear_frame(tid)

    async def bind_thread(self, thread_id: str, conn_id: str) -> None:
        async with self._lock:
            self._thread_to_conn[thread_id] = conn_id

    async def record_terminal_result(
        self, message_id: str, body: dict[str, Any]
    ) -> None:
        if not message_id:
            return
        async with _TERMINAL_RESULTS_LOCK:
            _TERMINAL_RESULTS[message_id] = (
                time.monotonic() + _TERMINAL_RESULT_TTL,
                body,
            )

    async def get_terminal_result(self, message_id: str) -> dict[str, Any] | None:
        async with _TERMINAL_RESULTS_LOCK:
            exp, body = _TERMINAL_RESULTS.get(message_id, (0.0, None))
            if exp > time.monotonic():
                return body
            _TERMINAL_RESULTS.pop(message_id, None)
        return None

    # -- push -----------------------------------------------------------

    async def push(self, thread_id: str, envelope: dict[str, Any]) -> bool:
        """Send an envelope to the connection owning `thread_id`."""
        async with self._lock:
            conn_id = self._thread_to_conn.get(thread_id)
            ws = self._conns.get(conn_id) if conn_id else None
        if ws is None:
            logger.debug(
                "[voice] push dropped (no connection for thread %s)", thread_id
            )
            return False
        try:
            await ws.send_json(envelope)
            return True
        except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
            logger.warning("[voice] push to thread %s failed: %s", thread_id, exc)
            return False


manager = VoiceConnectionManager()
