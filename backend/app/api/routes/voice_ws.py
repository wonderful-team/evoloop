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
from pydantic import BaseModel

from app.constants import DEFAULT_PROJECT_ID
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


# Throttle: only preheat when partial text has grown by ≥2 chars, max once per 500ms
_partial_last_text: dict[str, str] = {}
_partial_last_time: dict[str, float] = {}


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


async def _handle_route(body: dict[str, Any], conn_id: str) -> None:
    from app.core.routing import executor

    text = str(body.get("text", "")).strip()
    thread_id = str(body.get("thread_id", "")).strip()
    message_id = body.get("message_id")
    if not text or not thread_id:
        return

    project_id = int(body.get("project_id", DEFAULT_PROJECT_ID))

    t_total_start = time.time()

    # Lock phase: L0 check + dispatch (fast, no Worker execution)
    lock = await executor.get_thread_lock(thread_id)
    async with lock:
        # Check if a Worker is currently running
        from app.core.engine.worker_registry import worker_registry
        running_worker = await worker_registry.get_worker(thread_id)

        if not await voice_state_machine.can_accept_route(thread_id):
            if not running_worker:
                # No worker running, just barge-in the TTS
                await voice_state_machine.force_set(thread_id, VoiceSessionState.INTERRUPTED)
                logger.info("[voice] barge_in for thread %s", thread_id)
            # If a worker is running, don't cancel — Supervisor will decide
            # query vs new command in the agent context

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
            l0_match = matcher.match(text)
            l0_hit = l0_match is not None
            if not l0_hit:
                # L0 miss → dispatch to agent
                logger.info("[voice-perf] %s L0 miss → agent fast path (saved ~1-2s)", thread_id)
                from app.core.engine.dispatch import dispatch_agent_run
                from app.core.engine.background_agent import run_agent_background

                # If a worker is running, inject its info into metadata
                meta = {"source": "voice", "voice_thread_id": thread_id}
                old_worker_task = None
                if running_worker and running_worker.status == "running":
                    meta["has_running_worker"] = "true"
                    meta["running_worker_desc"] = running_worker.description
                    old_worker_task = running_worker.task

                await voice_state_machine.set(thread_id, VoiceSessionState.SPEAKING)
                await executor._mark_voice(thread_id, "agent")
                result = await dispatch_agent_run(
                    thread_id=thread_id, message_content=text,
                    project_id=project_id,
                    metadata=meta,
                )
                if result.status == "failed":
                    await executor.consume_voice(thread_id)
                    await executor.push_voice_result(thread_id, "failed",
                        getattr(result, "error", "") or "dispatch failed")
                else:
                    task = asyncio.create_task(
                        run_agent_background(thread_id, result.inputs)
                    )
                    await worker_registry.register_worker(thread_id, task,
                        description=running_worker.description if running_worker else "")
                    # Release lock before awaiting the long-running task
                # Lock released here via end of `async with lock`
            else:
                # L0 hit: push local result directly
                action, args = l0_match
                routed_body = {
                    "thread_id": thread_id, "status": "routed",
                    "target": {"type": "local", "action": action},
                    "params": args or {}, "candidates": [],
                }
                await manager.push(thread_id, _envelope(MessageType.VOICE_ROUTE_RESULT, routed_body))
                await voice_state_machine.set(thread_id, VoiceSessionState.IDLE)
        finally:
            ContextManager.reset(token)
    # Lock released — await Worker outside lock
    if not l0_hit and result and result.status != "failed":
        try:
            await task
        except asyncio.CancelledError:
            logger.info("[voice] agent task cancelled for thread %s", thread_id)
            await executor.consume_voice(thread_id)
            await executor.push_voice_result(thread_id, "cancelled", "")
        else:
            # Check if the new task cancelled the old worker or kept it running
            if old_worker_task is not None and not old_worker_task.done():
                # The old worker is still running — Supervisor decided QUERY
                # Re-register it so subsequent requests can see it
                await worker_registry.register_worker(
                    thread_id,
                    old_worker_task,
                    description=running_worker.description if running_worker else ""
                )
        total_ms = (time.time() - t_total_start) * 1000
        logger.info("[voice-perf] %s agent fast path total=%.0fms", thread_id, total_ms)


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


class StateUpdateRequest(BaseModel):
    key: str
    value: str


@router.post("/shared/state")
async def update_shared_state(req: StateUpdateRequest) -> dict:
    from app.core.shared_state import shared_state
    old, new = await shared_state.set(req.key, req.value)
    return {"ok": True, "key": req.key, "old": old, "new": new}


class TTSRequest(BaseModel):
    text: str
    engine: str = "cosyvoice"
    voice: str = "中文女"


@router.post("/tts")
async def generate_tts(req: TTSRequest) -> Any:
    from fastapi.responses import Response
    from app.infrastructure.voice.tts.factory import get_tts_provider
    from app.infrastructure.voice.tts.base import TTSOptions

    provider = await get_tts_provider(req.engine)
    result = await provider.generate(TTSOptions(text=req.text, voice=req.voice))
    return Response(content=result.audio_bytes, media_type="audio/wav")


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
