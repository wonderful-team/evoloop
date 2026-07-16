"""WebSocket endpoint for the voice-assistant thin client.

Loopback-only, no authentication (same-machine trusted subprocess; see design
§8). Request/result pairs are matched by `thread_id` over a single connection;
skill/agent execution is dispatched asynchronously and pushes its result back
over the same connection.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.context import ContextManager, EvoContext
from app.core.routing.connection import manager
from app.core.routing.deps import enforce_loopback_ws
from app.core.routing.idempotency import _ttl_seconds, is_duplicate
from app.core.schemas.canonical import (
    MessageType,
    create_envelope,
    is_canonical_envelope,
)
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

# message_id -> (monotonic expiry, routed body) so duplicate route requests can
# be answered with the cached result instead of silently hanging.
_DUPLICATE_ROUTE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_DUPLICATE_ROUTE_LOCK = asyncio.Lock()


def _store_routed_body(message_id: str | None, body: dict[str, Any]) -> None:
    if not message_id:
        return
    _DUPLICATE_ROUTE_CACHE[message_id] = (time.monotonic() + _ttl_seconds(), body)


async def _cached_routed_body(message_id: str) -> dict[str, Any] | None:
    async with _DUPLICATE_ROUTE_LOCK:
        exp, body = _DUPLICATE_ROUTE_CACHE.get(message_id, (0.0, None))
        if exp > time.monotonic():
            return body
        _DUPLICATE_ROUTE_CACHE.pop(message_id, None)
    return None


def _envelope(mtype: MessageType, body: dict[str, Any]) -> dict[str, Any]:
    return create_envelope(mtype, body).model_dump()


async def _handle_route(body: dict[str, Any], conn_id: str) -> None:
    from app.core.routing import executor, retriever
    from app.core.routing import router as route_router
    from app.core.routing.router import _top_k as _route_top_k
    from app.core.routing.schemas import RouteRequest

    text = str(body.get("text", "")).strip()
    thread_id = str(body.get("thread_id", "")).strip()
    message_id = body.get("message_id")
    if not text or not thread_id:
        return

    # Bind the request-scoped EvoContext so downstream tools (browser, etc.)
    # can resolve the current thread_id and provide per-thread isolation.
    ctx = EvoContext(thread_id=thread_id, request_id=message_id or gen_uuid())
    token = ContextManager.set(ctx)
    try:
        await manager.bind_thread(thread_id, conn_id)

        if message_id and await is_duplicate(str(message_id)):
            logger.info("[voice] duplicate route ignored: %s", message_id)
            terminal = await manager.get_terminal_result(str(message_id))
            if terminal is not None:
                await manager.push(
                    thread_id, _envelope(MessageType.VOICE_ROUTE_RESULT, terminal)
                )
                return
            cached = await _cached_routed_body(str(message_id))
            if cached is not None:
                await manager.push(
                    thread_id, _envelope(MessageType.VOICE_ROUTE_RESULT, cached)
                )
            else:
                await manager.push(
                    thread_id,
                    _envelope(
                        MessageType.VOICE_ROUTE_RESULT,
                        {
                            "thread_id": thread_id,
                            "status": "duplicate_no_cache",
                            "target": {"type": "noop"},
                            "params": {},
                            "candidates": [],
                        },
                    ),
                )
            return

        req = RouteRequest(text=text, thread_id=thread_id, message_id=message_id)
        candidates = await retriever.retrieve(text, top_k=_route_top_k())
        decisions = await route_router.route_many(req, candidates)

        decision = decisions[0]
        routed_body = {
            "thread_id": thread_id,
            "status": decision.status,
            "target": decision.target or {"type": decision.target_type},
            "params": {
                k: v for k, v in (decision.params or {}).items() if not k.startswith("_")
            },
            "candidates": [c.model_dump() for c in decision.candidates],
        }
        if len(decisions) > 1:
            routed_body["intents"] = len(decisions)
        _store_routed_body(message_id, routed_body)
        await manager.push(
            thread_id, _envelope(MessageType.VOICE_ROUTE_RESULT, routed_body)
        )

        if decision.target_type in ("skill", "macro", "agent"):
            asyncio.create_task(executor.execute_many(thread_id, decisions, message_id))
    finally:
        ContextManager.reset(token)

@router.websocket("/ws")
async def voice_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    if not await enforce_loopback_ws(websocket):
        return

    conn_id = gen_uuid()
    await manager.register(conn_id, websocket)
    await websocket.send_json(
        _envelope(MessageType.SYSTEM_INIT, {"client_id": conn_id, "device_key": ""})
    )
    logger.info("[voice] client connected: %s", conn_id)

    try:
        while True:
            data = await websocket.receive_json()
            if not is_canonical_envelope(data):
                await websocket.send_json(
                    _envelope(
                        MessageType.SYSTEM_ERROR,
                        {"code": "bad_envelope", "message": "not canonical"},
                    )
                )
                continue

            mtype = str(data.get("type", ""))
            body = data.get("body") or {}

            if mtype in ("connect", MessageType.SYSTEM_INIT):
                # Handshake carries only version/capability negotiation (no auth).
                await websocket.send_json(
                    _envelope(
                        MessageType.SYSTEM_INIT, {"client_id": conn_id, "ack": True}
                    )
                )
            elif mtype in (MessageType.VOICE_ROUTE, "voice.route"):
                body.setdefault("message_id", data.get("message_id"))
                asyncio.create_task(_handle_route(body, conn_id))
            elif mtype in (MessageType.VOICE_CANCEL, "voice.cancel"):
                # best-effort: real cancellation wired with per-thread task registry later.
                logger.info(
                    "[voice] cancel requested for thread %s", body.get("thread_id")
                )
            elif mtype == "ping":
                await websocket.send_json(
                    _envelope(MessageType.SYSTEM_INIT, {"pong": True})
                )
            else:
                await websocket.send_json(
                    _envelope(
                        MessageType.SYSTEM_ERROR,
                        {"code": "unknown_type", "message": mtype},
                    )
                )
    except WebSocketDisconnect:
        logger.info("[voice] client disconnected: %s", conn_id)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.warning("[voice] connection error: %s", exc)
    finally:
        await manager.unregister(conn_id)
