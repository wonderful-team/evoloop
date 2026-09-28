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
        async with self._lock:
            self._conns.pop(conn_id, None)
            stale = [tid for tid, cid in self._thread_to_conn.items() if cid == conn_id]
            for tid in stale:
                self._thread_to_conn.pop(tid, None)

    async def bind_thread(self, thread_id: str, conn_id: str) -> None:
        async with self._lock:
            self._thread_to_conn[thread_id] = conn_id

    async def is_thread_bound(self, thread_id: str) -> bool:
        """Return True if ``thread_id`` is currently bound to any active connection."""
        async with self._lock:
            return thread_id in self._thread_to_conn

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
            logger.warning(
                "[voice] push DROPPED — no connection for thread %s (conn_id=%s, known_threads=%s)",
                thread_id,
                conn_id,
                list(self._thread_to_conn.keys())[:5],
            )
            return False
        msg_type = envelope.get("type", "?")
        try:
            await ws.send_json(envelope)
            logger.info("[voice] push OK — type=%s thread=%s", msg_type, thread_id)
            return True
        except Exception as exc:
            logger.warning("[voice] push to thread %s failed: %s", thread_id, exc)
            return False

    async def broadcast(self, envelope: dict[str, Any]) -> None:
        """Broadcast an envelope to all connected WebSocket clients."""
        async with self._lock:
            connections = list(self._conns.values())
        for ws in connections:
            try:
                await ws.send_json(envelope)
            except Exception as exc:
                logger.warning("[voice] broadcast failed: %s", exc)


manager = VoiceConnectionManager()
