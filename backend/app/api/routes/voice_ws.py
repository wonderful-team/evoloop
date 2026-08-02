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
import json
import logging
import random
import time
from typing import Any

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.channel.output.voice_channel import VoiceChannel
from app.core.context import EvoContext
from app.core.routing.actions import ActionOutcome
from app.core.routing.deps import enforce_loopback_ws
from app.core.routing.dispatch_handler import dispatch_user_message
from app.core.routing.idempotency import is_duplicate
from app.core.routing.thread_locks import route_lock_scope
from app.core.schemas.canonical import MessageType, create_envelope, is_canonical_envelope
from app.core.voice.connection import manager
from app.core.voice.state_machine import VoiceSessionState, voice_state_machine
from app.core.voice import executor as voice_executor
from app.core.events import system_bus
from app.core.events.registry import SystemEventType
from app.core.events.schemas.lifecycle import ConfigChangedEvent
from app.infrastructure.voice.volc_dialog import VolcDialogClient
from app.infrastructure.config.service import SystemConfigService
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


def _envelope(mtype: MessageType | str, body: dict[str, Any]) -> dict[str, Any]:
    if isinstance(mtype, MessageType):
        return create_envelope(mtype, body).model_dump()
    return create_envelope(mtype, body).model_dump()


async def _handle_barge_in(thread_id: str) -> None:
    """Handle barge-in: stop TTS, update state machine.

    Does NOT cancel the background worker task. Only cancels the current
    streaming TTS segment.
    """
    from app.core.channel.output.voice_channel import VoiceChannel

    VoiceChannel.cancel_thread(thread_id)
    _is_sending_chat_tts_text[thread_id] = True
    await voice_state_machine.force_set(thread_id, VoiceSessionState.INTERRUPTED)
    await manager.push(thread_id, _envelope("voice.barge_in", {"thread_id": thread_id}))
    logger.info("[voice] barge_in mute-only for thread %s", thread_id)


async def _present_voice_outcome(thread_id: str, outcome: ActionOutcome) -> None:
    """Present L0 routing ActionOutcome to the voice channel."""
    from app.core.routing.routing_data import get_store
    from app.core.voice.executor import (
        handle_navigate,
        maybe_push_tts,
        push_local_result,
        push_macro_result,
    )

    if outcome.action_type == "navigate":
        route = outcome.data.get("route")
        feedback = outcome.data.get("feedback")
        if route:
            await handle_navigate(route, thread_id, feedback)
    elif outcome.action_type == "local":
        action = outcome.data.get("action", "")
        args = outcome.data.get("args", {})
        await push_local_result(thread_id, action, args)
        await maybe_push_tts(thread_id, get_store().builtin_responses["local"]["success"])
    elif outcome.action_type == "builtin":
        status = "done" if outcome.ok else "failed"
        if outcome.data.get("cancelled"):
            status = "cancelled"
        await push_macro_result(thread_id, status, outcome.message)
        if outcome.ok:
            await maybe_push_tts(thread_id, outcome.message)
    elif outcome.action_type == "macro":
        status = "done" if outcome.ok else "failed"
        await push_macro_result(thread_id, status, outcome.message)
        if outcome.ok:
            await maybe_push_tts(thread_id, outcome.message)


_thread_modes: dict[str, str] = {}

_voice_input_bound = False


async def _ensure_voice_input() -> None:
    global _voice_input_bound
    if _voice_input_bound:
        return
    from app.core.channel.input.voice_input import voice_input
    from app.core.engine.worker_registry import worker_registry
    from app.core.schemas.canonical import MessageType
    from app.core.voice.state_machine import VoiceSessionState, voice_state_machine

    voice_input.bind(
        manager=manager,
        executor=voice_executor,
        state_machine=voice_state_machine,
        state_enum=VoiceSessionState,
        worker_registry=worker_registry,
        envelope_fn=_envelope,
        message_type=MessageType,
    )
    # executor globals (manager/envelope_fn/message_type) are wired at app
    # startup in main.py, not here — so VoiceChannel works even if the Agent
    # is triggered by a non-route code path.
    _voice_input_bound = True


async def _handle_route(body: dict[str, Any], conn_id: str) -> None:
    from app.core.channel.input.voice_input import voice_input
    from app.core.engine.worker_registry import worker_registry

    await _ensure_voice_input()

    thread_id = str(body.get("thread_id", "")).strip()
    if not thread_id:
        return

    message_id = body.get("message_id")
    t_total_start = time.time()

    from app.core.identity import identity_service
    from app.core.shared_state import shared_state

    project_id = int(body.get("project_id", 0)) or int(await shared_state.get("project_id", "0"))
    member_id = await identity_service.get_member_id() or 0

    ctx = EvoContext(
        thread_id=thread_id,
        project_id=project_id,
        member_id=member_id,
        request_id=message_id or gen_uuid(),
    )

    async with route_lock_scope(thread_id, ctx):
        # Barge-in: if state can't accept route & no worker running
        if not await voice_state_machine.can_accept_route(thread_id):
            running_worker = await worker_registry.get_worker(thread_id)
            if not running_worker:
                await voice_state_machine.force_set(thread_id, VoiceSessionState.INTERRUPTED)
                logger.info("[voice] barge_in for thread %s", thread_id)

        await manager.bind_thread(thread_id, conn_id)
        await voice_state_machine.set(thread_id, VoiceSessionState.PROCESSING)

        # Idempotency
        if message_id and await is_duplicate(str(message_id)):
            terminal = await manager.get_terminal_result(str(message_id))
            if terminal is not None:
                await manager.push(thread_id, _envelope(MessageType.VOICE_ROUTE_RESULT, terminal))
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

        outcome = await dispatch_user_message(
            body,
            source="voice",
            input_channel=voice_input,
            thread_id=thread_id,
            project_id=project_id,
            member_id=member_id,
            context=ctx,
            worker_registry=worker_registry,
        )

        if outcome.handled:
            # L0 hit: restore chat TTS passthrough and present outcome
            if outcome.local_response:
                await _present_voice_outcome(thread_id, outcome.local_response)
            _is_sending_chat_tts_text.pop(thread_id, None)
            return

        if outcome.msg is None:
            # Invalid or empty payload — nothing to do.
            _is_sending_chat_tts_text.pop(thread_id, None)
            return

        # L0 miss → dispatch to agent
        logger.info("[voice-perf] %s L0 miss → agent dispatch", thread_id)

        post = await voice_input.post_dispatch(outcome.msg, outcome.inputs)
        if post is None:
            return

    # Lock released — await Worker outside lock
    running = await worker_registry.get_worker(thread_id)
    desc = running.description if running else ""
    await voice_input.await_and_finalize(
        thread_id,
        post.get("task"),
        post.get("old_worker_task"),
        worker_desc=desc,
    )
    total_ms = (time.time() - t_total_start) * 1000
    logger.info("[voice-perf] %s agent complete total=%.0fms", thread_id, total_ms)


async def _handle_dictation_finalize(body: dict[str, Any], conn_id: str) -> None:
    """Handle voice.dictation.finalize: LLM polish fallback (via ainvoke, no streaming)."""
    from app.infrastructure.config.service import SystemConfigService
    from app.infrastructure.llm.factory import LLMConfig, LLMFactory
    from app.utils.template import render_template

    raw_text = str(body.get("raw_text", "")).strip()
    thread_id = str(body.get("thread_id", "")).strip()
    if not raw_text:
        return

    await manager.bind_thread(thread_id, conn_id)

    # Check if dictation LLM polishing is enabled
    polish_enabled = SystemConfigService.get_value("EVOLOOP_DICTATION_LLM_POLISH", "true")
    if polish_enabled == "false":
        logger.info(f"[voice-ws] Dictation LLM polish is disabled, pushing raw text directly: {raw_text}")
        await manager.push(thread_id, _envelope("dictation.paste", {"text": raw_text}))
        await manager.push(
            thread_id,
            _envelope(
                MessageType.VOICE_DICTATION_POLISHED,
                {"changes": []},
            ),
        )
        return

    config = LLMConfig(model_name="", temperature=0.3, max_tokens=512)

    system_prompt = render_template("core/voice/dictation.md")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": raw_text},
    ]

    try:
        llm = await LLMFactory.create_llm(config)
        result = await llm.ainvoke(messages)
        content = ""
        if isinstance(result, dict):
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        elif hasattr(result, "content"):
            content = result.content

        polished = content.strip() or raw_text
        for tag in ("</s>", "<|im_end|>", "<|endoftext|>"):
            polished = polished.replace(tag, "")

        clarify_tag = "<CLARIFY>"
        if clarify_tag in polished:
            start = polished.find(clarify_tag) + len(clarify_tag)
            end = polished.find("</CLARIFY>", start)
            msg = polished[start:end] if end > start else polished[start:]
            await manager.push(
                thread_id,
                _envelope(
                    MessageType.VOICE_DICTATION_POLISHED,
                    {"changes": [{"clarify": msg}], "error": "clarify"},
                ),
            )
        else:
            # Paste polished text
            await manager.push(
                thread_id,
                _envelope("dictation.paste", {"text": polished.strip()}),
            )
            await manager.push(
                thread_id,
                _envelope(MessageType.VOICE_DICTATION_POLISHED, {"changes": []}),
            )
    except Exception as exc:
        logger.warning("[voice] dictation polish failed: %s", exc)
        # Fallback paste raw text
        await manager.push(
            thread_id,
            _envelope("dictation.paste", {"text": raw_text}),
        )
        await manager.push(
            thread_id,
            _envelope(MessageType.VOICE_DICTATION_POLISHED, {"changes": [], "error": str(exc)[:200]}),
        )


async def _on_config_changed_event(event: Any) -> None:
    try:
        if isinstance(event, ConfigChangedEvent):
            key = event.key
            old_val = event.old_value
            new_val = event.new_value
        else:
            data = getattr(event, "data", {}) or {}
            key = data.get("key", "")
            old_val = data.get("old_value", "")
            new_val = data.get("new_value", "")

        if key:
            await manager.broadcast(
                _envelope(
                    "system.config_changed",
                    {
                        "key": str(key),
                        "old_value": str(old_val or ""),
                        "new_value": str(new_val or ""),
                    },
                )
            )
    except Exception as exc:
        logger.error("[voice_ws] failed to broadcast config change: %s", exc)


system_bus.subscribe(SystemEventType.CONFIG_CHANGED, _on_config_changed_event)


async def _on_state_changed_event(event: Any) -> None:
    try:
        if hasattr(event, "key") and hasattr(event, "new_value"):
            await manager.broadcast(
                _envelope(
                    "system.state_changed",
                    {
                        "key": str(event.key),
                        "value": str(event.new_value),
                    },
                )
            )
    except Exception as exc:
        logger.error("[voice_ws] failed to broadcast state change: %s", exc)


system_bus.subscribe(SystemEventType.STATE_CHANGED, _on_state_changed_event)


class TTSRequest(BaseModel):
    text: str
    engine: str = "volcengine"
    voice: str = ""


async def generate_volc_tts(text: str, voice: str) -> bytes:
    app_id = SystemConfigService.get_value("SEEDUPLEX_APP_ID")
    access_key = SystemConfigService.get_value("SEEDUPLEX_ACCESS_KEY")
    if not app_id or not access_key:
        raise ValueError("火山引擎未配置 AppID/AccessKey")

    client = VolcDialogClient(app_id, access_key, session_id=gen_uuid())
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
    except asyncio.TimeoutError as exc:
        raise TimeoutError("Volcengine WebSocket 连接超时") from exc

    # Configure custom speaker if provided
    if voice:
        # We can dynamically set the speaker if Volcengine StartSession payload was custom.
        # But for now, we just trigger synthesis with default speaker.
        pass

    await client.send_chat_tts_text(start=True, end=True, content=text)
    audio_data = bytearray()
    try:
        while True:
            try:
                resp = await asyncio.wait_for(client.receive_response(), timeout=30)
            except asyncio.TimeoutError as exc:
                raise TimeoutError("等待 Volcengine TTS 音频超时") from exc
            mtype = resp.get("message_type")
            event = resp.get("event")
            payload = resp.get("payload_msg")

            if mtype == "SERVER_ACK" and isinstance(payload, bytes):
                audio_data.extend(payload)
            elif mtype == "SERVER_FULL_RESPONSE" and event == 359:
                break
    finally:
        await client.close()

    return bytes(audio_data)


@router.post("/tts")
async def generate_tts(req: TTSRequest) -> Any:
    from fastapi import HTTPException
    from fastapi.responses import Response

    t0 = time.time()
    try:
        audio_bytes = await generate_volc_tts(req.text, req.voice)
        logger.info(
            "[voice-ws] /tts generated %d bytes in %.1fs",
            len(audio_bytes),
            time.time() - t0,
        )
        return Response(content=audio_bytes, media_type="audio/pcm")
    except TimeoutError as exc:
        logger.error("[voice-ws] /tts timed out after %.1fs: %s", time.time() - t0, exc)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as e:
        logger.error(f"[voice-ws] generate_tts failed: {e}", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


session_modes: dict[str, str] = {}
_last_asr_text: dict[str, str] = {}
_is_sending_chat_tts_text: dict[str, bool] = {}
_volc_gen: dict[str, int] = {}  # generation counter for voice_receive_loop staleness


def unblock_voice_tts(thread_id: str) -> None:
    """Expose helper to unblock streaming TTS audio bytes immediately when text synthesis starts."""
    _is_sending_chat_tts_text[thread_id] = False


async def voice_receive_loop(
    websocket: WebSocket,
    volc_client: VolcDialogClient,
    thread_id: str,
    conn_id: str,
    mode: str,
    gen: int = 0,
):
    """Volcengine 接收循环 — ASR 事件共用，459/599 按 mode 分叉"""
    if mode == "dialogue":
        _is_sending_chat_tts_text[thread_id] = False
    try:
        while True:
            try:
                resp = await volc_client.receive_response()
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"[voice-ws] Volcengine connection closed for thread {thread_id} ({mode})")
                await volc_client.close()
                break

            mtype = resp.get("message_type")
            event = resp.get("event")
            payload = resp.get("payload_msg")

            if mtype == "SERVER_ACK":
                if mode == "dictation":
                    pass
                else:
                    flag = _is_sending_chat_tts_text.get(thread_id, False)
                    logger.debug(
                        "[voice-ws] SERVER_ACK payload_type=%s len=%s flag=%s",
                        type(payload),
                        len(payload) if isinstance(payload, (bytes, bytearray)) else 0,
                        flag,
                    )
                    if isinstance(payload, bytes):
                        if flag:
                            continue

                        try:
                            await websocket.send_bytes(payload)
                        except Exception as e:
                            logger.warning(f"[voice-ws] Failed to send audio bytes to Rust: {e}")
            elif mtype == "SERVER_FULL_RESPONSE":
                # --- Shared: event 451 ASR partial ---
                if event == 451 and isinstance(payload, dict):
                    extra = payload.get("extra") or {}
                    asr_text = (extra.get("origin_text") or "").strip()
                    if not asr_text:
                        results = payload.get("results") or []
                        if results:
                            alts = results[0].get("alternatives") or []
                            if alts:
                                asr_text = (alts[0].get("text") or "").strip()
                    if asr_text:
                        _last_asr_text[thread_id] = asr_text
                        if mode == "dialogue":
                            try:
                                await websocket.send_json(
                                    _envelope(
                                        "voice.partial",
                                        {"thread_id": thread_id, "text": asr_text},
                                    )
                                )
                            except Exception:
                                logger.debug("[voice-ws] failed to send ASR partial for %s", thread_id, exc_info=True)

                # --- Shared: event 450 barge-in ---
                if event == 450:
                    if mode == "dialogue":
                        await _handle_barge_in(thread_id)
                    else:
                        try:
                            await websocket.send_json(_envelope(MessageType.VOICE_BARGE_IN, {"thread_id": thread_id}))
                        except Exception:
                            logger.debug("[voice-ws] failed to forward barge_in for %s", thread_id, exc_info=True)

                # --- Fork: event 459 ASR done ---
                elif event == 459:
                    asr_text = _last_asr_text.pop(thread_id, None) or ""
                    if not asr_text and isinstance(payload, dict):
                        extra = payload.get("extra") or {}
                        asr_text = (extra.get("origin_text") or "").strip()
                    if asr_text:
                        logger.info(f"[voice-ws] ASR done: {asr_text} ({mode})")
                        if mode == "dialogue":
                            try:
                                await websocket.send_json(
                                    _envelope(
                                        "voice.partial",
                                        {"thread_id": thread_id, "text": asr_text},
                                    )
                                )
                            except Exception:
                                logger.debug("[voice-ws] failed to send ASR done partial for %s", thread_id, exc_info=True)
                            _is_sending_chat_tts_text[thread_id] = True
                            asyncio.create_task(_run_agent_pipeline(websocket, thread_id, asr_text))
                        else:
                            await manager.bind_thread(thread_id, conn_id)
                            asyncio.create_task(
                                _handle_dictation_finalize(
                                    {
                                        "raw_text": asr_text,
                                        "thread_id": thread_id,
                                        "target_locale": "zh",
                                    },
                                    conn_id,
                                )
                            )

                # --- Dialogue-only: event 359 TTS play ended ---
                elif event == 359 and mode == "dialogue":
                    _is_sending_chat_tts_text[thread_id] = False
                    await voice_state_machine.set(thread_id, VoiceSessionState.LISTENING)
                    try:
                        await websocket.send_json(
                            _envelope(
                                "voice:state",
                                {"state": "listening", "thread_id": thread_id},
                            )
                        )
                    except Exception:
                        logger.debug("[voice-ws] failed to send listening state for %s", thread_id, exc_info=True)

                # --- Dialogue-only: event 550/559 ChatTTSText ack ---
                elif event in (550, 559) and mode == "dialogue":
                    if event == 559:
                        logger.debug("[voice-ws] Event %s for thread %s", event, thread_id)

                # --- Dialogue-only: event 350 injected TTS start ---
                elif event == 350 and isinstance(payload, dict) and mode == "dialogue":
                    tts_type = payload.get("tts_type", "")
                    logger.info(
                        "[voice-ws] Event 350 tts_type=%r for thread %s",
                        tts_type,
                        thread_id,
                    )
                    if tts_type in ("chat_tts_text", "external_rag"):
                        _is_sending_chat_tts_text[thread_id] = False

                # --- Fork: event 599 ASR timeout ---
                elif event == 599 and _last_asr_text.get(thread_id):
                    asr_text = _last_asr_text.pop(thread_id, "")
                    logger.info(f"[voice-ws] ASR timeout: {asr_text} ({mode})")
                    if mode == "dialogue":
                        asyncio.create_task(_run_agent_pipeline(websocket, thread_id, asr_text))
                    else:
                        await manager.bind_thread(thread_id, conn_id)
                        asyncio.create_task(_handle_dictation_finalize({
                            "raw_text": asr_text,
                            "thread_id": thread_id,
                            "target_locale": "zh",
                        }, conn_id))

            elif mtype == "SERVER_ERROR":
                logger.error(f"[voice-ws] Volcengine error: {payload}")
                try:
                    await websocket.send_json(
                        _envelope(
                            MessageType.SYSTEM_ERROR,
                            {"code": "volc_error", "message": str(payload)},
                        )
                    )
                except Exception:
                    logger.debug("[voice-ws] failed to forward volc error for %s", thread_id, exc_info=True)
            else:
                logger.debug(
                    "[voice-ws] unhandled event %s %s for thread %s",
                    mtype,
                    event,
                    thread_id,
                )
    except asyncio.CancelledError:
        logger.debug("[voice-ws] Voice receive loop cancelled for thread %s", thread_id)
        # Normal cancellation (voice.stop / mode switch) — WS stays open
    except Exception as e:
        logger.error(f"[voice-ws] Voice receive loop error ({mode}): {e}", exc_info=e)
        # Do NOT call websocket.close() here — the websocket object is shared
        # with the main event loop and closing it would terminate the connection
        # for all tasks, causing "Cannot call 'receive' once a disconnect..."
        # The Rust side will detect the Volcengine error via missing responses.
    finally:
        # Only clean up per-thread state if this is still the current
        # generation.  Otherwise a stale task (from a previous voice.start)
        # would destroy state for the active session.
        if _volc_gen.get(thread_id, 0) == gen:
            await voice_state_machine.clear(thread_id)
            _volc_gen.pop(thread_id, None)
            _last_asr_text.pop(thread_id, None)
            _is_sending_chat_tts_text.pop(thread_id, None)


async def _run_agent_pipeline(websocket: WebSocket, thread_id: str, text: str) -> None:
    from app.core.channel.input.voice_input import voice_input
    from app.core.engine.worker_registry import worker_registry

    await _ensure_voice_input()

    from app.core.identity import identity_service
    from app.core.shared_state import shared_state

    project_id = int(await shared_state.get("project_id", "0"))
    member_id = await identity_service.get_member_id() or 0

    ctx = EvoContext(
        thread_id=thread_id,
        project_id=project_id,
        member_id=member_id,
        request_id=gen_uuid(),
    )

    try:
        async with route_lock_scope(thread_id, ctx):
            # Clear any previous barge-in cancellation so the new agent response
            # can stream TTS again.
            VoiceChannel.reset_thread(thread_id)
            await voice_state_machine.set(thread_id, VoiceSessionState.PROCESSING)
            try:
                await websocket.send_json(
                    _envelope("voice:state", {"state": "processing", "thread_id": thread_id})
                )
            except Exception:
                logger.debug("[voice-ws] failed to send processing state for %s", thread_id, exc_info=True)

            outcome = await dispatch_user_message(
                {"thread_id": thread_id, "text": text},
                source="voice",
                input_channel=voice_input,
                thread_id=thread_id,
                project_id=project_id,
                member_id=member_id,
                context=ctx,
                worker_registry=worker_registry,
            )
            if outcome.handled:
                if outcome.local_response:
                    await _present_voice_outcome(thread_id, outcome.local_response)
                return

            if outcome.msg is None:
                return

            # --- EARLY ACK ---
            if outcome and not outcome.handled and outcome.msg:
                from app.core.engine.domain_mapping import ACK_TEMPLATES
                ack_text = random.choice(ACK_TEMPLATES)
                if ack_text:
                    await VoiceChannel.push_tts_chunk(thread_id, ack_text, end=True, force_start=True)
                    VoiceChannel.reset_tts_started(thread_id)

            logger.info("[voice-perf] %s L0 miss → agent dispatch", thread_id)
            post = await voice_input.post_dispatch(outcome.msg, outcome.inputs)
            if post is None:
                return

        # Lock released — await Worker outside lock
        running = await worker_registry.get_worker(thread_id)
        desc = running.description if running else ""
        await voice_input.await_and_finalize(
            thread_id,
            post.get("task"),
            post.get("old_worker_task"),
            worker_desc=desc,
        )
    except Exception as e:
        logger.error("[voice-ws] Agent pipeline failed: %s", e, exc_info=e)


@router.websocket("/ws")
async def voice_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    if not await enforce_loopback_ws(websocket):
        return

    conn_id = gen_uuid()
    await manager.register(conn_id, websocket)

    configs = {cfg.key: cfg.value for cfg in SystemConfigService.get_all()}
    from app.core.shared_state import shared_state

    state = await shared_state.get_all()
    await websocket.send_json(
        _envelope(
            MessageType.SYSTEM_INIT,
            {
                "client_id": conn_id,
                "device_key": "",
                "configs": configs,
                "state": state,
            },
        )
    )
    logger.info("[voice] client connected: %s (sent %d config keys, %d state keys)", conn_id, len(configs), len(state))

    volc_client: VolcDialogClient | None = None
    volc_receive_task: asyncio.Task | None = None
    active_threads: set[str] = set()

    try:
        while True:
            # Receive raw message frame (supports both text/JSON and binary bytes)
            raw_msg = await websocket.receive()

            # Handle WebSocket disconnect message (Starlette may return this
            # as a dict instead of raising WebSocketDisconnect in some edge cases)
            if raw_msg.get("type") == "websocket.disconnect":
                logger.info("[voice-ws] received disconnect message, code=%s", raw_msg.get("code"))
                break

            # 1. Binary audio frame from Rust (microphone PCM)
            if "bytes" in raw_msg:
                pcm_bytes = raw_msg["bytes"]
                if volc_client:
                    await volc_client.send_audio(pcm_bytes)
                continue

            # 2. Text/JSON message
            if "text" not in raw_msg:
                continue

            data = json.loads(raw_msg["text"])
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
                configs = {cfg.key: cfg.value for cfg in SystemConfigService.get_all()}
                await websocket.send_json(
                    _envelope(
                        MessageType.SYSTEM_INIT,
                        {
                            "client_id": conn_id,
                            "ack": True,
                            "configs": configs,
                        },
                    )
                )
            elif mtype in (MessageType.VOICE_ROUTE, "voice.route"):
                body.setdefault("message_id", data.get("message_id"))
                _route_task = asyncio.create_task(_handle_route(body, conn_id))

                route_tid = str(body.get("thread_id", ""))

                def _on_route_done(t: asyncio.Task, route_tid: str = route_tid) -> None:
                    if t.cancelled():
                        return
                    exc = t.exception()
                    if exc is not None:
                        logger.error("[voice] route task failed: %s", exc, exc_info=exc)
                        if route_tid:
                            asyncio.create_task(
                                manager.push(
                                    route_tid,
                                    _envelope(
                                        MessageType.VOICE_ROUTE_RESULT,
                                        {
                                            "thread_id": route_tid,
                                            "status": "failed",
                                            "summary": "处理出错",
                                        },
                                    ),
                                )
                            )

                _route_task.add_done_callback(_on_route_done)
            elif mtype in (MessageType.VOICE_CANCEL, "voice.cancel"):
                thread_id = str(body.get("thread_id", "")).strip()
                if thread_id:
                    await voice_executor.cancel_voice_task(thread_id)
                    await voice_state_machine.force_set(thread_id, VoiceSessionState.IDLE)
                    _is_sending_chat_tts_text.pop(thread_id, None)
                    _last_asr_text.pop(thread_id, None)
                    logger.info("[voice] cancel for thread %s", thread_id)
            elif mtype in (MessageType.VOICE_BARGE_IN, "voice.barge_in"):
                thread_id = str(body.get("thread_id", "")).strip()
                if thread_id:
                    await asyncio.create_task(_handle_barge_in(thread_id))
            elif mtype in ("voice.start",):
                thread_id = str(body.get("thread_id", "")).strip()
                if not thread_id:
                    continue
                await manager.bind_thread(thread_id, conn_id)
                VoiceChannel.reset_thread(thread_id)
                if not await voice_state_machine.can_accept_route(thread_id):
                    await _handle_barge_in(thread_id)

                # Store session mode early so the receive loop knows how to behave
                mode = str(body.get("mode", "dialogue")).strip()
                session_modes[thread_id] = mode
                logger.info(f"[voice-ws] Starting session for thread {thread_id} in {mode} mode")

                app_id = SystemConfigService.get_value("SEEDUPLEX_APP_ID")
                access_key = SystemConfigService.get_value("SEEDUPLEX_ACCESS_KEY")
                if not app_id or not access_key:
                    logger.warning("[voice-ws] Volcengine app_id/access_key not configured")
                    await voice_state_machine.force_set(thread_id, VoiceSessionState.IDLE)
                    await websocket.send_json(
                        _envelope(
                            MessageType.SYSTEM_ERROR,
                            {
                                "code": "volc_not_configured",
                                "message": "火山引擎未配置 AppID/AccessKey",
                            },
                        )
                    )
                    await websocket.send_json(
                        _envelope(
                            "voice:state",
                            {"state": "idle", "thread_id": thread_id},
                        )
                    )
                    continue

                # Cancel the old receive task BEFORE closing the client,
                # so the task gets CancelledError (clean exit) rather than
                # waking up to find self.ws is None (RuntimeError → websocket.close).
                if volc_receive_task:
                    volc_receive_task.cancel()
                    volc_receive_task = None
                if volc_client:
                    await volc_client.close()
                    volc_client = None

                from app.core.voice.executor import active_volc_clients

                # Bump generation so any stale voice_receive_loop's
                # finally won't touch the state machine.
                gen = _volc_gen.get(thread_id, 0) + 1
                _volc_gen[thread_id] = gen
                volc_client = VolcDialogClient(app_id, access_key, session_id=thread_id)
                try:
                    await volc_client.connect()
                    active_volc_clients[thread_id] = volc_client
                    volc_receive_task = asyncio.create_task(
                        voice_receive_loop(
                            websocket,
                            volc_client,
                            thread_id,
                            conn_id,
                            mode,
                            gen=gen,
                        )
                    )
                    logger.info(f"[voice-ws] Connected VolcDialogClient for thread {thread_id} in {mode} mode")

                    # Only announce "listening" after Volcengine is actually ready.
                    await voice_state_machine.set(thread_id, VoiceSessionState.LISTENING)
                    active_threads.add(thread_id)
                    await websocket.send_json(
                        _envelope(
                            "voice:state",
                            {"state": "listening", "thread_id": thread_id},
                        )
                    )
                except Exception as e:
                    logger.exception("[voice-ws] VolcDialogClient connect failed: %s", e)
                    await voice_state_machine.force_set(thread_id, VoiceSessionState.IDLE)
                    await websocket.send_json(
                        _envelope(
                            MessageType.SYSTEM_ERROR,
                            {"code": "volc_connect_failed", "message": str(e)},
                        )
                    )
                    await websocket.send_json(
                        _envelope(
                            "voice:state",
                            {"state": "idle", "thread_id": thread_id},
                        )
                    )
            elif mtype in ("voice.stop",):
                thread_id = str(body.get("thread_id", "")).strip()
                if thread_id:
                    current = await voice_state_machine.get(thread_id)
                    if current in (
                        VoiceSessionState.LISTENING,
                        VoiceSessionState.SPEAKING,
                        VoiceSessionState.PROCESSING,
                        VoiceSessionState.INTERRUPTED,
                    ):
                        await voice_state_machine.set(thread_id, VoiceSessionState.IDLE)
                    active_threads.discard(thread_id)
                    session_modes.pop(thread_id, None)
                    _last_asr_text.pop(thread_id, None)
                    _is_sending_chat_tts_text.pop(thread_id, None)
                    _volc_gen.pop(thread_id, None)

                    # Clean up Volcengine client
                    from app.core.voice.executor import active_volc_clients

                    active_volc_clients.pop(thread_id, None)
                    if volc_client:
                        await volc_client.close()
                        volc_client = None
                    if volc_receive_task:
                        volc_receive_task.cancel()
                        volc_receive_task = None

                    try:
                        await websocket.send_json(
                            _envelope(
                                "voice:state",
                                {"state": "idle", "thread_id": thread_id},
                            )
                        )
                    except Exception:
                        logger.debug("[voice-ws] failed to send idle state on stop for %s", thread_id, exc_info=True)
            elif mtype in (MessageType.VOICE_DICTATION_FINALIZE, "voice.dictation.finalize"):
                asyncio.create_task(_handle_dictation_finalize(body, conn_id))
            elif mtype == "ping":
                await websocket.send_json(_envelope(MessageType.SYSTEM_INIT, {"pong": True}))
            else:
                await websocket.send_json(
                    _envelope(
                        MessageType.SYSTEM_ERROR,
                        {"code": "unknown_type", "message": mtype},
                    )
                )
    except WebSocketDisconnect:
        logger.info("[voice] client disconnected: %s", conn_id)
    except Exception as exc:
        logger.exception("[voice] connection error: %s", exc)
    finally:
        # Clean up Volcengine clients and tasks
        if volc_client:
            try:
                await volc_client.close()
            except Exception:
                logger.debug("[voice-ws] volc_client.close() raised, ignoring", exc_info=True)
        if volc_receive_task:
            volc_receive_task.cancel()
        from app.core.routing.conversation_state import clear_thread_intent_state_for_threads
        from app.core.voice.executor import active_volc_clients

        # Only clear per-thread global state if this connection still owns it.
        # A Rust reconnect may have already started a new connection for the
        # same thread_id; in that case the new connection is responsible for
        # cleaning up and we must not destroy its active Volcengine client or
        # wipe conversation intent state.
        threads_to_clear_intent: list[str] = []
        for tid in active_threads:
            if volc_client is not None and active_volc_clients.get(tid) is volc_client:
                active_volc_clients.pop(tid, None)
            if not await manager.is_thread_bound(tid):
                session_modes.pop(tid, None)
                threads_to_clear_intent.append(tid)
                _last_asr_text.pop(tid, None)
                _is_sending_chat_tts_text.pop(tid, None)
                _volc_gen.pop(tid, None)
        if threads_to_clear_intent:
            clear_thread_intent_state_for_threads(threads_to_clear_intent)
        await manager.unregister(conn_id)
