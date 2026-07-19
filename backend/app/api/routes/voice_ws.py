"""WebSocket endpoint for the voice-assistant thin client.

Loopback-only, no authentication (same-machine trusted subprocess; see design
§8). Request/result pairs are matched by `thread_id` over a single connection;
skill/agent execution is dispatched asynchronously and pushes its result back
over the same connection.

Full-duplex streaming extensions (voice.token, voice.tts_boundary, voice.partial,
voice.barge_in) enable near-real-time conversation with barge-in support.
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
from app.core.routing.idempotency import is_duplicate
from app.core.schemas.canonical import (
    MessageType,
    create_envelope,
    is_canonical_envelope,
)
from app.core.voice.state_machine import VoiceSessionState, voice_state_machine
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


def _envelope(mtype: MessageType | str, body: dict[str, Any]) -> dict[str, Any]:
    if isinstance(mtype, MessageType):
        return create_envelope(mtype, body).model_dump()
    return create_envelope(mtype, body).model_dump()


async def _handle_barge_in(thread_id: str) -> None:
    """Handle barge-in: cancel current task, update state machine."""
    from app.core.routing import executor

    lock = await executor.get_thread_lock(thread_id)
    async with lock:
        cancelled = await executor.cancel_voice_task(thread_id)
        await voice_state_machine.force_set(thread_id, VoiceSessionState.INTERRUPTED)
        logger.info("[voice] barge_in for thread %s, cancelled=%s", thread_id, cancelled)


async def _handle_partial(body: dict[str, Any]) -> None:
    """Handle voice.partial: preheat retrieval with partial transcript."""
    from app.core.routing import retriever as retriever_mod

    text = str(body.get("text", "")).strip()
    thread_id = str(body.get("thread_id", "")).strip()
    if not text or not thread_id:
        return
    try:
        await retriever_mod.preheat(thread_id, text)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.debug("[voice] preheat failed: %s", exc)


async def _handle_route(body: dict[str, Any], conn_id: str) -> None:
    from app.core.routing import executor

    text = str(body.get("text", "")).strip()
    thread_id = str(body.get("thread_id", "")).strip()
    message_id = body.get("message_id")
    if not text or not thread_id:
        return

    t_total_start = time.time()
    lock = await executor.get_thread_lock(thread_id)
    async with lock:
        # Auto barge-in: if TTS is still playing, cancel current task first
        if not await voice_state_machine.can_accept_route(thread_id):
            cancelled = await executor.cancel_voice_task(thread_id)
            await voice_state_machine.force_set(thread_id, VoiceSessionState.INTERRUPTED)
            logger.info("[voice] barge_in for thread %s, cancelled=%s", thread_id, cancelled)

        ctx = EvoContext(thread_id=thread_id, request_id=message_id or gen_uuid())
        token = ContextManager.set(ctx)
        try:
            await manager.bind_thread(thread_id, conn_id)
            await voice_state_machine.set(thread_id, VoiceSessionState.PROCESSING)

            if message_id and await is_duplicate(str(message_id)):
                logger.info("[voice] duplicate route ignored: %s", message_id)
                terminal = await manager.get_terminal_result(str(message_id))
                if terminal is not None:
                    await manager.push(
                        thread_id, _envelope(MessageType.VOICE_ROUTE_RESULT, terminal)
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

            # Fast path: pre-check L0 before expensive LLM routing
            from app.core.routing.router import _get_local_matcher
            matcher = await _get_local_matcher()
            l0_hit = matcher.match(text) is not None
            if not l0_hit:
                # L0 miss → skip LLM route, dispatch to agent directly
                logger.info("[voice-perf] %s L0 miss → agent fast path (saved ~1-2s)", thread_id)
                # Dispatch agent directly
                from app.core.engine.dispatch import dispatch_agent_run
                from app.core.engine.background_agent import run_agent_background
                from app.constants import DEFAULT_PROJECT_ID
                await voice_state_machine.set(thread_id, VoiceSessionState.SPEAKING)
                await executor._mark_voice(thread_id, "agent")
                result = await dispatch_agent_run(
                    thread_id=thread_id, message_content=text,
                    project_id=DEFAULT_PROJECT_ID,
                    metadata={"source": "voice", "voice_thread_id": thread_id},
                )
                if result.status == "failed":
                    await executor.consume_voice(thread_id)
                    await executor.push_voice_result(thread_id, "failed",
                        getattr(result, "error", "") or "dispatch failed")
                else:
                    task = asyncio.create_task(
                        run_agent_background(thread_id, result.inputs)
                    )
                    await executor.register_voice_task(thread_id, task)
                    try:
                        await task
                    except asyncio.CancelledError:
                        logger.info("[voice] agent task cancelled for thread %s", thread_id)
                        await executor.consume_voice(thread_id)
                        await executor.push_voice_result(thread_id, "cancelled", "")
                total_ms = (time.time() - t_total_start) * 1000
                logger.info("[voice-perf] %s agent fast path total=%.0fms", thread_id, total_ms)
                return

            # L0 hit: push local result directly
            action, args = matcher.match(text)
            routed_body = {
                "thread_id": thread_id, "status": "routed",
                "target": {"type": "local", "action": action},
                "params": args or {}, "candidates": [],
            }
            await manager.push(thread_id, _envelope(MessageType.VOICE_ROUTE_RESULT, routed_body))
            await voice_state_machine.set(thread_id, VoiceSessionState.IDLE)

        finally:
            ContextManager.reset(token)


async def _handle_dictation_finalize(body: dict[str, Any], conn_id: str) -> None:
    """Handle voice.dictation.finalize: cloud LLM polish fallback."""
    from app.core.routing.executor import stream_llm_response
    from app.infrastructure.config.service import SystemConfigService
    from app.utils.template import render_template

    raw_text = str(body.get("raw_text", "")).strip()
    thread_id = str(body.get("thread_id", "")).strip()
    target_locale = str(body.get("target_locale", "zh"))
    if not raw_text:
        return

    await manager.bind_thread(thread_id, conn_id)

    model_name = SystemConfigService.get_value("LLM_MODEL")
    if not model_name:
        await manager.push(
            thread_id,
            _envelope(
                MessageType.VOICE_DICTATION_POLISHED,
                {"polished_text": raw_text, "changes": [], "error": "no model configured"},
            ),
        )
        return

    system_prompt = render_template("core/voice/dictation.md")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": raw_text},
    ]

    try:
        polished = await stream_llm_response(
            thread_id, messages, model_name, temperature=0.3, max_tokens=512
        )
        await manager.push(
            thread_id,
            _envelope(
                MessageType.VOICE_DICTATION_POLISHED,
                {"polished_text": polished.strip(), "raw_text": raw_text, "changes": []},
            ),
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as exc:
        logger.warning("[voice] dictation polish failed: %s", exc)
        await manager.push(
            thread_id,
            _envelope(
                MessageType.VOICE_DICTATION_POLISHED,
                {"polished_text": raw_text, "changes": [], "error": str(exc)[:200]},
            ),
        )


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
                await websocket.send_json(
                    _envelope(
                        MessageType.SYSTEM_INIT, {"client_id": conn_id, "ack": True}
                    )
                )
            elif mtype in (MessageType.VOICE_ROUTE, "voice.route"):
                body.setdefault("message_id", data.get("message_id"))
                asyncio.create_task(_handle_route(body, conn_id))
            elif mtype in (MessageType.VOICE_CANCEL, "voice.cancel"):
                thread_id = str(body.get("thread_id", "")).strip()
                if thread_id:
                    from app.core.routing import executor
                    await executor.cancel_voice_task(thread_id)
                    await voice_state_machine.force_set(thread_id, VoiceSessionState.IDLE)
                    logger.info("[voice] cancel for thread %s", thread_id)
            elif mtype in (MessageType.VOICE_BARGE_IN, "voice.barge_in"):
                thread_id = str(body.get("thread_id", "")).strip()
                if thread_id:
                    asyncio.create_task(_handle_barge_in(thread_id))
            elif mtype in (MessageType.VOICE_PARTIAL, "voice.partial"):
                asyncio.create_task(_handle_partial(body))
            elif mtype in ("voice.start",):
                thread_id = str(body.get("thread_id", "")).strip()
                if thread_id:
                    await manager.bind_thread(thread_id, conn_id)
                    if not await voice_state_machine.can_accept_route(thread_id):
                        await _handle_barge_in(thread_id)
                    await voice_state_machine.set(thread_id, VoiceSessionState.LISTENING)
            elif mtype in ("voice.stop",):
                thread_id = str(body.get("thread_id", "")).strip()
                if thread_id:
                    current = await voice_state_machine.get(thread_id)
                    if current == VoiceSessionState.LISTENING:
                        await voice_state_machine.set(thread_id, VoiceSessionState.IDLE)
            elif mtype in (MessageType.VOICE_DICTATION_FINALIZE, "voice.dictation.finalize"):
                asyncio.create_task(_handle_dictation_finalize(body, conn_id))
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
