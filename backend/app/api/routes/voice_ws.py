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
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.infrastructure.voice.volc_dialog import VolcDialogClient
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
    """Handle barge-in: cancel current task, update state machine.

    Does NOT acquire the route lock — barge-in is an interrupt signal, not a
    new route. ``cancel_voice_task`` → ``task.cancel()`` propagates
    ``CancelledError`` into ``_dispatch_macro`` / ``await_and_finalize``,
    which push ``cancelled`` to the WS. The state machine's ``force_set``
    overrides whatever the in-flight route set (PROCESSING/SPEAKING →
    INTERRUPTED), which is the correct semantics.
    """
    from app.core.routing import executor

    cancelled = await executor.cancel_voice_task(thread_id)
    _is_sending_chat_tts_text[thread_id] = True
    await voice_state_machine.force_set(thread_id, VoiceSessionState.INTERRUPTED)
    logger.info("[voice] barge_in for thread %s, cancelled=%s", thread_id, cancelled)


# Throttle: only preheat when partial text has grown by ≥2 chars, max once per 500ms
_partial_last_text: dict[str, str] = {}
_partial_last_time: dict[str, float] = {}
_thread_modes: dict[str, str] = {}


async def _handle_partial(body: dict[str, Any]) -> None:
    """Handle voice.partial: preheat retrieval with partial transcript."""
    from app.core.routing import retriever as retriever_mod

    text = str(body.get("text", "")).strip()
    thread_id = str(body.get("thread_id", "")).strip()
    if not text or not thread_id:
        return

    # Throttle: only preheat on significant progress
    last_text = _partial_last_text.get(thread_id, "")
    last_time = _partial_last_time.get(thread_id, 0.0)
    now = time.time()
    if len(text) - len(last_text) < 2 and now - last_time < 0.5:
        _partial_last_text[thread_id] = text
        _partial_last_time[thread_id] = now
        return

    _partial_last_text[thread_id] = text
    _partial_last_time[thread_id] = now
    try:
        await retriever_mod.preheat(thread_id, text)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        logger.debug("[voice] preheat failed: %s", exc)


_voice_input_bound = False


async def _ensure_voice_input() -> None:
    global _voice_input_bound
    if _voice_input_bound:
        return
    from app.core.channel.input.voice_input import voice_input
    from app.core.routing import executor as voice_executor
    from app.core.engine.worker_registry import worker_registry
    from app.core.voice.state_machine import VoiceSessionState, voice_state_machine
    from app.core.schemas.canonical import MessageType

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
    from app.core.routing import executor
    from app.core.channel.input.voice_input import voice_input

    await _ensure_voice_input()

    thread_id = str(body.get("thread_id", "")).strip()
    if not thread_id:
        return

    message_id = body.get("message_id")
    t_total_start = time.time()

    # Lock phase: input processing (L0 check + dispatch is fast)
    lock = await executor.get_thread_lock(thread_id)
    async with lock:
        from app.core.engine.worker_registry import worker_registry

        # Barge-in: if state can't accept route & no worker running
        if not await voice_state_machine.can_accept_route(thread_id):
            running_worker = await worker_registry.get_worker(thread_id)
            if not running_worker:
                await voice_state_machine.force_set(thread_id, VoiceSessionState.INTERRUPTED)
                logger.info("[voice] barge_in for thread %s", thread_id)

        from app.core.shared_state import shared_state
        project_id = int(body.get("project_id", 0)) or int(await shared_state.get("project_id", "0"))
        ctx = EvoContext(thread_id=thread_id, project_id=project_id, request_id=message_id or gen_uuid())
        token = ContextManager.set(ctx)
        try:
            await manager.bind_thread(thread_id, conn_id)
            await voice_state_machine.set(thread_id, VoiceSessionState.PROCESSING)

            # Idempotency
            if message_id and await is_duplicate(str(message_id)):
                terminal = await manager.get_terminal_result(str(message_id))
                if terminal is not None:
                    await manager.push(thread_id, _envelope(MessageType.VOICE_ROUTE_RESULT, terminal))
                else:
                    await manager.push(thread_id, _envelope(MessageType.VOICE_ROUTE_RESULT, {
                        "thread_id": thread_id, "status": "duplicate_no_cache",
                        "target": {"type": "noop"}, "params": {}, "candidates": [],
                    }))
                return

            # Let VoiceInputChannel decide: L0 match → local push, L0 miss → IncomingMessage
            msg = await voice_input.receive(body)
            if msg is None:
                # L0 hit or invalid — handled internally (push + state transition)
                return

            # L0 miss → dispatch to agent
            logger.info("[voice-perf] %s L0 miss → agent dispatch", thread_id)
            # State set to SPEAKING inside voice_input.receive()

            result = await voice_input.dispatch(msg)
            post = await voice_input.post_dispatch(msg, result)
            if post is None:
                # dispatch failed — handled internally
                return
            task = post["task"]
        finally:
            ContextManager.reset(token)
    # Lock released — await Worker outside lock
    if msg is not None:
        from app.core.engine.worker_registry import worker_registry
        running = await worker_registry.get_worker(thread_id)
        desc = running.description if running else ""
        post = post or {}
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
    target_locale = str(body.get("target_locale", "zh"))
    if not raw_text:
        return

    await manager.bind_thread(thread_id, conn_id)

    # Check if dictation LLM polishing is enabled
    polish_enabled = SystemConfigService.get_value("EVOLOOP_DICTATION_LLM_POLISH", "true")
    if polish_enabled == "false":
        logger.info(f"[voice-ws] Dictation LLM polish is disabled, pushing raw text directly: {raw_text}")
        await manager.push(thread_id, _envelope(
            MessageType.VOICE_DICTATION_POLISHED,
            {"polished_text": raw_text, "raw_text": raw_text, "changes": []},
        ))
        return

    model_name = SystemConfigService.get_value("LLM_MODEL")
    if not model_name:
        await manager.push(thread_id, _envelope(
            MessageType.VOICE_DICTATION_POLISHED,
            {"polished_text": raw_text, "changes": [], "error": "no model configured"},
        ))
        return

    system_prompt = render_template("core/voice/dictation.md")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": raw_text},
    ]

    try:
        config = LLMConfig(model_name=model_name, temperature=0.3, max_tokens=512)
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
            await manager.push(thread_id, _envelope(
                MessageType.VOICE_DICTATION_POLISHED,
                {"polished_text": raw_text, "changes": [{"clarify": msg}], "error": "clarify"},
            ))
        else:
            await manager.push(thread_id, _envelope(
                MessageType.VOICE_DICTATION_POLISHED,
                {"polished_text": polished.strip(), "raw_text": raw_text, "changes": []},
            ))
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as exc:
        logger.warning("[voice] dictation polish failed: %s", exc)
        await manager.push(thread_id, _envelope(
            MessageType.VOICE_DICTATION_POLISHED,
            {"polished_text": raw_text, "changes": [], "error": str(exc)[:200]},
        ))


class DictationRequest(BaseModel):
    raw_text: str
    target_locale: str = "zh"


class DictationResponse(BaseModel):
    polished_text: str
    raw_text: str
    changes: list = []


@router.post("/dictation")
async def dictation_polish(req: DictationRequest) -> DictationResponse:
    """HTTP endpoint for dictation text polishing.

    Uses LLMFactory (two-tier: local lightning model if available, else cloud)
    to polish ASR output, following the same strategy as Supervisor.
    """
    from app.infrastructure.config.service import SystemConfigService
    from app.infrastructure.llm.factory import LLMConfig, LLMFactory
    from app.utils.template import render_template

    polish_enabled = SystemConfigService.get_value("EVOLOOP_DICTATION_LLM_POLISH", "true")
    if polish_enabled == "false":
        return DictationResponse(
            polished_text=req.raw_text,
            raw_text=req.raw_text,
            changes=[],
        )

    model_name = SystemConfigService.get_value("LLM_MODEL")
    if not model_name:
        return DictationResponse(
            polished_text=req.raw_text,
            raw_text=req.raw_text,
            changes=[{"error": "LLM_MODEL not configured"}],
        )

    system_prompt = render_template("core/voice/dictation.md")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": req.raw_text},
    ]

    config = LLMConfig(model_name=model_name, temperature=0.3, max_tokens=512)
    llm = await LLMFactory.create_llm(config)
    result = await llm.ainvoke(messages)
    content = ""
    if isinstance(result, dict):
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    elif hasattr(result, "content"):
        content = result.content

    polished = content.strip() or req.raw_text
    # Strip LLM artifacts
    for tag in ("</s>", "<|im_end|>", "<|endoftext|>"):
        polished = polished.replace(tag, "")
    # Handle CLARIFY: unable to understand
    clarify_tag = "<CLARIFY>"
    if clarify_tag in polished:
        start = polished.find(clarify_tag) + len(clarify_tag)
        end = polished.find("</CLARIFY>", start)
        msg = polished[start:end] if end > start else polished[start:]
        return DictationResponse(
            polished_text=req.raw_text,
            raw_text=req.raw_text,
            changes=[{"clarify": msg}],
        )
    return DictationResponse(
        polished_text=polished.strip(),
        raw_text=req.raw_text,
    )


from app.core.events import system_bus
from app.core.events.registry import SystemEventType
from app.core.events.schemas.lifecycle import ConfigChangedEvent
from app.infrastructure.config.service import SystemConfigService


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
                _envelope("system.config_changed", {
                    "key": str(key),
                    "old_value": str(old_val or ""),
                    "new_value": str(new_val or ""),
                })
            )
    except Exception as exc:
        logger.error("[voice_ws] failed to broadcast config change: %s", exc)


system_bus.subscribe(SystemEventType.CONFIG_CHANGED, _on_config_changed_event)


async def _on_state_changed_event(event: Any) -> None:
    try:
        if hasattr(event, "key") and hasattr(event, "new_value"):
            await manager.broadcast(
                _envelope("system.state_changed", {
                    "key": str(event.key),
                    "value": str(event.new_value),
                })
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
    await client.connect()
    
    # Configure custom speaker if provided
    if voice:
        # We can dynamically set the speaker if Volcengine StartSession payload was custom.
        # But for now, we just trigger synthesis with default speaker.
        pass

    await client.send_chat_tts_text(start=True, end=True, content=text)
    audio_data = bytearray()
    try:
        while True:
            resp = await client.receive_response()
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
    from fastapi.responses import Response
    from fastapi import HTTPException
    try:
        audio_bytes = await generate_volc_tts(req.text, req.voice)
        return Response(content=audio_bytes, media_type="audio/pcm")
    except Exception as e:
        logger.error(f"[voice-ws] generate_tts failed: {e}", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


session_modes: dict[str, str] = {}
_last_asr_text: dict[str, str] = {}
_is_sending_chat_tts_text: dict[str, bool] = {}


async def dialogue_receive_loop(websocket: WebSocket, volc_client: VolcDialogClient, thread_id: str, conn_id: str):
    """Volcengine 接收循环 — 对话模式：ASR → Agent → TTS 音频"""
    import websockets
    _is_sending_chat_tts_text[thread_id] = False
    try:
        while True:
            try:
                resp = await volc_client.receive_response()
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"[voice-ws] Dialogue Volcengine connection closed for thread {thread_id}")
                break

            mtype = resp.get("message_type")
            event = resp.get("event")
            payload = resp.get("payload_msg")

            if mtype == "SERVER_ACK":
                if isinstance(payload, bytes):
                    if _is_sending_chat_tts_text.get(thread_id, False):
                        logger.debug("[voice-ws] discarded %d audio bytes (discarding auto TTS)", len(payload))
                        continue
                    logger.info("[voice-ws] ===> forwarding %d audio bytes to Rust", len(payload))
                    try:
                        await websocket.send_bytes(payload)
                    except Exception as e:
                        logger.warning(f"[voice-ws] Failed to send audio bytes to Rust: {e}")
            elif mtype == "SERVER_FULL_RESPONSE":
                # event 451: ASR partial result
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
                        logger.info(f"[voice-ws] ASR partial: {asr_text}")
                        try:
                            await websocket.send_json(
                                _envelope("voice.partial", {"thread_id": thread_id, "text": asr_text})
                            )
                        except Exception:
                            pass
                        from app.core.routing import retriever as retriever_mod
                        asyncio.create_task(retriever_mod.preheat(thread_id, asr_text))

                # event 450: barge-in / user starts speaking
                if event == 450:
                    from app.core.routing import executor
                    await executor.cancel_voice_task(thread_id)
                    _is_sending_chat_tts_text[thread_id] = True
                    await voice_state_machine.force_set(thread_id, VoiceSessionState.INTERRUPTED)
                    try:
                        await websocket.send_json(
                            _envelope(MessageType.VOICE_BARGE_IN, {"thread_id": thread_id})
                        )
                    except Exception:
                        pass

                # event 459: ASR done → discard auto TTS, send placeholder, run Agent
                elif event == 459:
                    asr_text = _last_asr_text.pop(thread_id, None) or ""
                    if not asr_text and isinstance(payload, dict):
                        extra = payload.get("extra") or {}
                        asr_text = (extra.get("origin_text") or "").strip()
                    if asr_text:
                        logger.info(f"[voice-ws] Dialogue ASR: {asr_text}")
                        try:
                            await websocket.send_json(
                                _envelope("voice.partial", {"thread_id": thread_id, "text": asr_text})
                            )
                        except Exception:
                            pass
                        _is_sending_chat_tts_text[thread_id] = True
                        asyncio.create_task(_run_agent_pipeline(websocket, thread_id, asr_text))

                # event 359: TTS play ended
                elif event == 359:
                    _is_sending_chat_tts_text[thread_id] = False
                    await voice_state_machine.set(thread_id, VoiceSessionState.LISTENING)
                    try:
                        await websocket.send_json(
                            _envelope("voice:state", {"state": "listening", "thread_id": thread_id})
                        )
                    except Exception:
                        pass

                # event 550/559: ChatTTSText acknowledgment
                elif event in (550, 559):
                    logger.debug("[voice-ws] Event %s for thread %s", event, thread_id)

                # event 350: injected TTS starting (ChatTTSText/ChatRAGText)
                elif event == 350 and isinstance(payload, dict):
                    tts_type = payload.get("tts_type", "")
                    logger.info("[voice-ws] Event 350 tts_type=%r for thread %s", tts_type, thread_id)
                    if tts_type in ("chat_tts_text", "external_rag"):
                        pass

                # event 599: ASR idle timeout
                elif event == 599 and _last_asr_text.get(thread_id):
                    asr_text = _last_asr_text.pop(thread_id, "")
                    logger.info(f"[voice-ws] Dialogue ASR timeout: {asr_text}")
                    asyncio.create_task(_run_agent_pipeline(websocket, thread_id, asr_text))

            elif mtype == "SERVER_ERROR":
                logger.error(f"[voice-ws] Volcengine error: {payload}")
                try:
                    await websocket.send_json(
                        _envelope(MessageType.SYSTEM_ERROR, {"code": "volc_error", "message": str(payload)})
                    )
                except Exception:
                    pass
            else:
                logger.debug("[voice-ws] unhandled event %s %s for thread %s", mtype, event, thread_id)
    except asyncio.CancelledError:
        logger.debug("[voice-ws] Dialogue receive loop cancelled for thread %s", thread_id)
        pass
    except Exception as e:
        logger.error(f"[voice-ws] Dialogue receive loop error: {e}", exc_info=e)


async def dictation_receive_loop(websocket: WebSocket, volc_client: VolcDialogClient, thread_id: str, conn_id: str):
    """Volcengine 接收循环 — 听写模式：ASR → dictation.paste"""
    import websockets
    try:
        while True:
            try:
                resp = await volc_client.receive_response()
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"[voice-ws] Dictation Volcengine connection closed for thread {thread_id}")
                break
            if not resp:
                await asyncio.sleep(0.01)
                continue

            mtype = resp.get("message_type")
            event = resp.get("event")
            payload = resp.get("payload_msg")

            if mtype == "SERVER_ACK":
                # Skip TTS audio — dictation only needs text
                pass
            elif mtype == "SERVER_FULL_RESPONSE":
                # event 451: ASR partial result
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
                        logger.info(f"[voice-ws] ASR partial: {asr_text}")

                # event 450: barge-in / user starts speaking
                if event == 450:
                    try:
                        await websocket.send_json(
                            _envelope(MessageType.VOICE_BARGE_IN, {"thread_id": thread_id})
                        )
                    except Exception:
                        pass

                # event 459: ASR done → paste
                elif event == 459:
                    asr_text = _last_asr_text.pop(thread_id, None) or ""
                    if not asr_text and isinstance(payload, dict):
                        extra = payload.get("extra") or {}
                        asr_text = (extra.get("origin_text") or "").strip()
                    if asr_text:
                        logger.info(f"[voice-ws] Dictation ASR: {asr_text}")
                        # Paste text to active application
                        try:
                            await websocket.send_json({
                                "type": "dictation.paste",
                                "body": {"text": asr_text},
                                "message_id": gen_uuid(),
                            })
                        except Exception as e:
                            logger.warning(f"[voice-ws] dictation.paste failed: {e}")
                        # LLM polish (async, non-blocking)
                        from app.core.routing.connection import manager
                        await manager.bind_thread(thread_id, conn_id)
                        asyncio.create_task(_handle_dictation_finalize(
                            {"raw_text": asr_text, "thread_id": thread_id, "target_locale": "zh"},
                            conn_id
                        ))

                # event 599: ASR idle timeout → paste
                elif event == 599 and _last_asr_text.get(thread_id):
                    asr_text = _last_asr_text.pop(thread_id, "")
                    logger.info(f"[voice-ws] Dictation ASR timeout: {asr_text}")
                    try:
                        await websocket.send_json({
                            "type": "dictation.paste",
                            "body": {"text": asr_text},
                            "message_id": gen_uuid(),
                        })
                    except Exception as e:
                        logger.warning(f"[voice-ws] dictation.paste failed: {e}")
                    from app.core.routing.connection import manager
                    await manager.bind_thread(thread_id, conn_id)
                    asyncio.create_task(_handle_dictation_finalize(
                        {"raw_text": asr_text, "thread_id": thread_id, "target_locale": "zh"},
                        conn_id
                    ))

            elif mtype == "SERVER_ERROR":
                logger.error(f"[voice-ws] Volcengine error: {payload}")
                try:
                    await websocket.send_json(
                        _envelope(MessageType.SYSTEM_ERROR, {"code": "volc_error", "message": str(payload)})
                    )
                except Exception:
                    pass
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"[voice-ws] Dictation receive loop error: {e}", exc_info=e)


async def _run_agent_pipeline(websocket: WebSocket, thread_id: str, text: str):
    from app.core.channel.input.voice_input import voice_input
    from app.core.routing import executor

    await _ensure_voice_input()

    lock = await executor.get_thread_lock(thread_id)
    async with lock:
        try:
            # Set state to PROCESSING
            await voice_state_machine.set(thread_id, VoiceSessionState.PROCESSING)
            await websocket.send_json(
                _envelope("voice:state", {"state": "processing", "thread_id": thread_id})
            )

            body = {
                "thread_id": thread_id,
                "text": text,
            }
            msg = await voice_input.receive(body)
            if msg is None:
                # L0 matched locally (e.g. macro or builtin) - handled internally
                return

            logger.info("[voice-perf] %s L0 miss → agent dispatch", thread_id)
            result = await voice_input.dispatch(msg)
            post = await voice_input.post_dispatch(msg, result)
            if post is None:
                return

            # Wait for the agent task to complete
            task = post["task"]
            old_worker_task = post["old_worker_task"]

            from app.core.engine.worker_registry import worker_registry
            running = await worker_registry.get_worker(thread_id)
            desc = running.description if running else ""

            await voice_input.await_and_finalize(
                thread_id,
                task,
                old_worker_task,
                worker_desc=desc,
            )
        except Exception as e:
            logger.error(f"[voice-ws] Agent pipeline failed: {e}", exc_info=e)


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
        _envelope(MessageType.SYSTEM_INIT, {
            "client_id": conn_id,
            "device_key": "",
            "configs": configs,
            "state": state,
        })
    )
    logger.info("[voice] client connected: %s (sent %d config keys, %d state keys)", conn_id, len(configs), len(state))

    volc_client: Optional[VolcDialogClient] = None
    volc_receive_task: Optional[asyncio.Task] = None
    active_threads: set[str] = set()

    try:
        while True:
            # Receive raw message frame (supports both text/JSON and binary bytes)
            raw_msg = await websocket.receive()
            
            # 1. Binary audio frame from Rust (microphone PCM)
            if "bytes" in raw_msg:
                pcm_bytes = raw_msg["bytes"]
                if volc_client:
                    await volc_client.send_audio(pcm_bytes)
                else:
                    logger.warning("[voice-ws] received %d bytes but no VolcEngine client", len(pcm_bytes))
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
                        MessageType.SYSTEM_INIT, {
                            "client_id": conn_id,
                            "ack": True,
                            "configs": configs,
                        }
                    )
                )
            elif mtype in (MessageType.VOICE_ROUTE, "voice.route"):
                body.setdefault("message_id", data.get("message_id"))
                _route_task = asyncio.create_task(_handle_route(body, conn_id))

                def _on_route_done(t: asyncio.Task) -> None:
                    if t.cancelled():
                        return
                    exc = t.exception()
                    if exc is not None:
                        logger.error("[voice] route task failed: %s", exc, exc_info=exc)
                        tid = str(body.get("thread_id", ""))
                        if tid:
                            asyncio.create_task(manager.push(
                                tid, _envelope(MessageType.VOICE_ROUTE_RESULT, {
                                    "thread_id": tid, "status": "failed",
                                    "summary": "处理出错",
                                })
                            ))

                _route_task.add_done_callback(_on_route_done)
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
                    active_threads.add(thread_id)
                    
                    # Notify Rust client of the listening state
                    try:
                        await websocket.send_json(
                            _envelope("voice.state", {"state": "listening", "thread_id": thread_id})
                        )
                    except Exception:
                        pass

                    # Store session mode
                    mode = str(body.get("mode", "dialogue")).strip()
                    session_modes[thread_id] = mode
                    logger.info(f"[voice-ws] Starting session for thread {thread_id} in {mode} mode")

                    # Initialize and connect Volcengine client dynamically
                    app_id = SystemConfigService.get_value("SEEDUPLEX_APP_ID")
                    access_key = SystemConfigService.get_value("SEEDUPLEX_ACCESS_KEY")
                    if app_id and access_key:
                        if volc_client:
                            await volc_client.close()
                            volc_client = None
                        if volc_receive_task:
                            volc_receive_task.cancel()
                            volc_receive_task = None

                        from app.core.routing.executor import active_volc_clients
                        volc_client = VolcDialogClient(app_id, access_key, session_id=thread_id)
                        try:
                            await volc_client.connect()
                            active_volc_clients[thread_id] = volc_client
                            # 根据 mode 选择不同的 receive loop
                            mode = str(body.get("mode", "dialogue")).strip()
                            if mode == "dictation":
                                volc_receive_task = asyncio.create_task(dictation_receive_loop(websocket, volc_client, thread_id, conn_id))
                            else:
                                volc_receive_task = asyncio.create_task(dialogue_receive_loop(websocket, volc_client, thread_id, conn_id))
                            logger.info(f"[voice-ws] Connected VolcDialogClient for thread {thread_id} in {mode} mode")
                        except Exception as e:
                            logger.error(f"[voice-ws] VolcDialogClient connect failed: {e}", exc_info=e)
                            await websocket.send_json(
                                _envelope(MessageType.SYSTEM_ERROR, {"code": "volc_connect_failed", "message": str(e)})
                            )
                    else:
                        logger.warning("[voice-ws] Volcengine app_id/access_key not configured")
                        await websocket.send_json(
                            _envelope(MessageType.SYSTEM_ERROR, {"code": "volc_not_configured", "message": "火山引擎未配置 AppID/AccessKey"})
                        )
            elif mtype in ("voice.stop",):
                thread_id = str(body.get("thread_id", "")).strip()
                if thread_id:
                    current = await voice_state_machine.get(thread_id)
                    if current in (VoiceSessionState.LISTENING, VoiceSessionState.SPEAKING, VoiceSessionState.PROCESSING):
                        await voice_state_machine.set(thread_id, VoiceSessionState.IDLE)
                    active_threads.discard(thread_id)
                    session_modes.pop(thread_id, None)
                    _last_asr_text.pop(thread_id, None)
                    _is_sending_chat_tts_text.pop(thread_id, None)

                    # Clean up Volcengine client
                    from app.core.routing.executor import active_volc_clients
                    active_volc_clients.pop(thread_id, None)
                    if volc_client:
                        await volc_client.close()
                        volc_client = None
                    if volc_receive_task:
                        volc_receive_task.cancel()
                        volc_receive_task = None
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
        # Clean up Volcengine clients and tasks
        if volc_client:
            await volc_client.close()
        if volc_receive_task:
            volc_receive_task.cancel()
        from app.core.routing.executor import active_volc_clients
        for tid in active_threads:
            active_volc_clients.pop(tid, None)
            session_modes.pop(tid, None)
            _last_asr_text.pop(tid, None)
            _is_sending_chat_tts_text.pop(tid, None)
        await manager.unregister(conn_id)

