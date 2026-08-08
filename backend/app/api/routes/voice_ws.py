"""WebSocket endpoint for the voice-assistant thin client.

Loopback-only, no authentication (same-machine trusted subprocess; see design
§8). Request/result pairs are matched by `thread_id` over a single connection;
skill/agent execution is dispatched asynchronously and pushes its result back
over the same connection.

Full-duplex streaming extensions (voice.token, voice.tts_boundary, voice.partial,
voice.barge_in) enable near-real-time conversation with barge-in support.
"""

from __future__ import annotations

import array
import asyncio
import json
import logging
import math
import time
from collections import deque
from typing import Any

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.channel.output.voice_channel import VoiceChannel
from app.core.context import EvoContext
from app.core.events import system_bus
from app.core.events.registry import SystemEventType
from app.core.events.schemas.lifecycle import ConfigChangedEvent
from app.core.routing.actions import ActionOutcome
from app.core.routing.deps import enforce_loopback_ws
from app.core.routing.dispatch_handler import dispatch_user_message
from app.core.routing.idempotency import is_duplicate
from app.core.routing.thread_locks import route_lock_scope
from app.core.schemas.canonical import (
    Endpoint,
    EndpointKind,
    MessageType,
    create_envelope,
    is_canonical_envelope,
)
from app.core.voice import executor as voice_executor
from app.core.voice.connection import manager
from app.core.voice.state_machine import VoiceSessionState, voice_state_machine
from app.infrastructure.config.service import SystemConfigService
from app.infrastructure.voice.volc_asr import VolcAsrClient
from app.infrastructure.voice.volc_tts import VolcTtsClient, s16le_to_f32le
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])


def _envelope(mtype: MessageType | str, body: dict[str, Any]) -> dict[str, Any]:
    return create_envelope(
        mtype,
        body,
        source=Endpoint(kind=EndpointKind.BACKEND),
        target=Endpoint(kind=EndpointKind.VOICE),
    ).model_dump()


async def _handle_barge_in(thread_id: str) -> None:
    """Handle barge-in: stop TTS, update state machine.

    Does NOT cancel the background worker task. Only cancels the current
    streaming TTS segment.
    """
    from app.core.channel.output.voice_channel import VoiceChannel

    VoiceChannel.cancel_thread(thread_id)
    _is_sending_chat_tts_text[thread_id] = True
    await voice_state_machine.force_set(thread_id, VoiceSessionState.INTERRUPTED)
    await manager.push(
        thread_id,
        _envelope(MessageType.VOICE_BARGE_IN, {"thread_id": thread_id})
    )
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
        await maybe_push_tts(thread_id, get_store().responses["local"]["success"])
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
    from app.core.voice.state_machine import VoiceSessionState, voice_state_machine

    voice_input.bind(
        executor=voice_executor,
        state_machine=voice_state_machine,
        state_enum=VoiceSessionState,
        worker_registry=worker_registry,
    )
    # VoiceChannel's WS transport (manager/envelope_fn/message_type) is wired
    # at app startup in main.py via VoiceChannel.bind(...), so VoiceChannel
    # works even if the Agent is triggered by a non-route code path.
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
    from app.core.state import shared_state

    project_id = int(body.get("project_id", 0)) or int(
        await shared_state.get("project_id", "0")
    )
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
                await voice_state_machine.force_set(
                    thread_id, VoiceSessionState.INTERRUPTED
                )
                logger.info("[voice] barge_in for thread %s", thread_id)

        await manager.bind_thread(thread_id, conn_id)
        await voice_state_machine.set(thread_id, VoiceSessionState.PROCESSING)

        # Idempotency
        if message_id and await is_duplicate(str(message_id)):
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
    polish_enabled = SystemConfigService.get_value("EVOLOOP_DICTATION_LLM_POLISH")
    if polish_enabled == "false":
        logger.info(
            f"[voice-ws] Dictation LLM polish is disabled, pushing raw text directly: {raw_text}"
        )
        await manager.push(
            thread_id, _envelope(MessageType.DICTATION_PASTE, {"text": raw_text})
        )
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
            content = (
                result.get("choices", [{}])[0].get("message", {}).get("content", "")
            )
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
                _envelope(MessageType.DICTATION_PASTE, {"text": polished.strip()}),
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
            _envelope(MessageType.DICTATION_PASTE, {"text": raw_text}),
        )
        await manager.push(
            thread_id,
            _envelope(
                MessageType.VOICE_DICTATION_POLISHED,
                {"changes": [], "error": str(exc)[:200]},
            ),
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
                    MessageType.SYSTEM_CONFIG_CHANGED,
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
                    MessageType.SYSTEM_STATE_CHANGED,
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

    client = VolcTtsClient(app_id, access_key, session_id=gen_uuid())
    speaker = voice or VolcTtsClient.DEFAULT_SPEAKER
    try:
        await asyncio.wait_for(client.connect(), timeout=15)
    except TimeoutError as exc:
        raise TimeoutError("Volcengine TTS WebSocket 连接超时") from exc
    try:
        await client.start_session(speaker)
        await client.send_text(text)
        await client.finish_session()
        audio_data = await client.receive_audio(timeout=30.0)
    except TimeoutError as exc:
        raise TimeoutError("等待 Volcengine TTS 音频超时") from exc
    finally:
        await client.close()

    return audio_data


@router.post("/tts")
async def generate_tts(req: TTSRequest) -> Any:
    from fastapi import HTTPException
    from fastapi.responses import Response

    if not req.text or not req.text.strip():
        raise HTTPException(status_code=422, detail="text 不能为空")

    t0 = time.time()
    try:
        audio_bytes = await generate_volc_tts(req.text, req.voice)
        logger.info(
            "[voice-ws] /tts generated %d bytes in %.1fs",
            len(audio_bytes),
            time.time() - t0,
        )
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except TimeoutError as exc:
        logger.error("[voice-ws] /tts timed out after %.1fs: %s", time.time() - t0, exc)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as e:
        logger.error(f"[voice-ws] generate_tts failed: {e}", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


class VoiceTtsBridge:
    """VoiceChannel 的 TTS 文本 → 火山流式 TTS → 音频帧实时转发给 Rust。

    真正的流式：VoiceChannel 已按句切分调用 send_chat_tts_text，这里每句
    立即独立合成（复用同一 WS 连接），352 音频帧边到达边转发给播放端，
    与 Agent 生成下一句并行播放。替代原实时对话的 ChatTTSText 出口。
    """

    def __init__(self, thread_id: str, conn_id: str, send_audio_cb) -> None:
        self.thread_id = thread_id
        self.conn_id = conn_id
        self._send_audio_cb = send_audio_cb
        self._client: VolcTtsClient | None = None
        self._lock = asyncio.Lock()
        self.ws: object | None = None  # 兼容 VoiceChannel 的 .ws 检查

    async def reconnect(self) -> None:
        return None

    async def connect(self) -> None:
        """预连接 TTS（voice.start 时调用），失败不影响主流程，首播时惰性重试。"""
        async with self._lock:
            try:
                await self._ensure_client()
            except Exception:
                logger.debug(
                    "[voice-ws] bridge TTS pre-connect failed for %s",
                    self.conn_id,
                    exc_info=True,
                )

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                logger.debug("[voice-ws] bridge TTS close failed", exc_info=True)
            self._client = None

    async def _ensure_client(self) -> VolcTtsClient:
        if self._client is None:
            app_id = SystemConfigService.get_value("SEEDUPLEX_APP_ID")
            access_key = SystemConfigService.get_value("SEEDUPLEX_ACCESS_KEY")
            if not app_id or not access_key:
                raise ValueError("火山引擎未配置 AppID/AccessKey")
            client = VolcTtsClient(app_id, access_key, session_id=gen_uuid())
            try:
                await asyncio.wait_for(client.connect(), timeout=15)
            except asyncio.TimeoutError as exc:
                raise TimeoutError("Volcengine TTS WebSocket 连接超时") from exc
            self._client = client
        return self._client

    async def send_chat_tts_text(self, start: bool, end: bool, content: str) -> None:
        text = (content or "").strip()
        if not text:
            return
        async with self._lock:
            try:
                client = await self._ensure_client()
                session_id = gen_uuid()
                # 火山 'pcm' 输出 s16le 24k，转成 f32le 匹配 Rust 语音客户端契约
                await client.start_session(
                    client.DEFAULT_SPEAKER, session_id=session_id, format="pcm"
                )
                await client.send_text(text, session_id=session_id)
                await client.finish_session(session_id=session_id)
                # 按实时播放速率节流转发：Volc 合成快于实时（~5x），若一次性灌给
                # 客户端，Rust 的 2s ring buffer 会溢出丢采样导致后半句加速。
                # 最多提前 1.2s 音频（防溢出），低于该值时立即发送（防欠载）。
                t0 = time.monotonic()
                sent_audio_s = 0.0
                _TTS_BUDGET_S = 1.2
                barge_in_break = False
                async for chunk in client.receive_audio_stream(session_id=session_id):
                    # barge-in: user spoke over the TTS — drop the rest of this
                    # sentence instead of refilling the client's playout queue.
                    if _is_sending_chat_tts_text.get(self.thread_id, False):
                        logger.info(
                            "[voice-ws] bridge TTS muted by barge-in for %s",
                            self.thread_id,
                        )
                        barge_in_break = True
                        break
                    if chunk and self._send_audio_cb is not None:
                        await self._send_audio_cb(s16le_to_f32le(chunk))
                        sent_audio_s += len(chunk) / 2 / 24000.0
                        ahead = sent_audio_s - (time.monotonic() - t0)
                        if ahead > _TTS_BUDGET_S:
                            await asyncio.sleep(ahead - _TTS_BUDGET_S)
                if barge_in_break:
                    # barge-in 中断时服务端仍在合成该句剩余文本，旧会话的 352 音频帧
                    # 会残留在 WS 缓冲。关闭连接让下一句重建，避免残留帧被误播或
                    # 污染下一句的 start_session 握手响应。
                    try:
                        await client.close()
                    except Exception:
                        logger.debug(
                            "[voice-ws] bridge TTS close after barge-in failed for %s",
                            self.conn_id,
                            exc_info=True,
                        )
                    self._client = None
            except Exception:
                logger.exception(
                    "[voice-ws] bridge TTS failed for %s, will reconnect", self.conn_id
                )
                if self._client is not None:
                    try:
                        await self._client.close()
                    except Exception:
                        logger.debug("[voice-ws] bridge TTS close failed after run error", exc_info=True)
                    self._client = None


async def _register_dialogue_tts_bridge(
    thread_id: str, conn_id: str, websocket: WebSocket
) -> None:
    """把 dialogue 的 TTS 出口注册到 active_volc_clients 并预连接（VoiceChannel 靠它找 TTS）。

    复用同一连接已注册的 bridge（含其预连接），避免每次定案/重连重建导致连接泄漏。
    仅当 conn_id 变化（Rust 重连）或没有 bridge 时才重建。
    """
    from app.core.voice.executor import active_volc_clients

    cur = active_volc_clients.get(thread_id)
    if isinstance(cur, VoiceTtsBridge) and cur.conn_id == conn_id:
        return
    if isinstance(cur, VoiceTtsBridge):
        try:
            await cur.close()
        except Exception:
            logger.debug(
                "[voice-ws] bridge close failed on replace for %s",
                thread_id,
                exc_info=True,
            )
    bridge = VoiceTtsBridge(
        thread_id,
        conn_id,
        lambda audio, ws=websocket: ws.send_bytes(audio),
    )
    active_volc_clients[thread_id] = bridge
    await bridge.connect()


session_modes: dict[str, str] = {}
_last_asr_text: dict[str, str] = {}
_asr_audio_log: dict[str, int] = {}
_is_sending_chat_tts_text: dict[str, bool] = {}
_volc_gen: dict[str, int] = {}  # generation counter for voice_receive_loop staleness

# --- Auto-segmentation (dictation continuous mode) ---
# Dictation mode stays ON after the F12 long-press is released. The backend
# detects a silence window (user finished an utterance), finalizes the current
# ASR segment (negative packet -> collect -> paste), then reconnects a fresh
# VolcAsrClient for the next segment (bigmodel_async closes the connection
# after the negative packet — verified by probe).
_DICT_AUTO_SEGMENT_MS: float = 800.0
_DICT_SILENCE_RMS: float = 400.0
_dict_silence_ms: dict[str, float] = {}  # conn_id -> accumulated silence ms
_conn_thread: dict[str, str] = {}  # conn_id -> current thread_id

# VAD 门控：无人说话时不上传静音帧到火山（按时长计费资源），省费用。
# 检测到语音后先补发最近 _VAD_PREROLL_FRAMES 帧（音头保护），进入
# SPEAKING 态持续上传；静音回落到 _DICT_AUTO_SEGMENT_MS 后按既有逻辑
# 定案或退回 PREROLL。注意 bigmodel_async 服务端 8s 收不到包就会
# 结束会话（"waiting next packet timeout"），所以 PREROLL 期间用
# 小块静音帧做 keepalive（~0.7% 实时时长，几乎不耗费用）。
_VAD_STATE_PREROLL = "preroll"
_VAD_STATE_SPEAKING = "speaking"
_VAD_PREROLL_FRAMES: int = 16  # ~320ms @ 20ms frame
_VAD_KEEPALIVE_INTERVAL_MS: float = 3_000.0
_VAD_IDLE_RECONNECT_MS: float = 300_000.0
_vad_state: dict[str, str] = {}  # conn_id -> VAD_STATE_*
_vad_preroll: dict[str, deque[bytes]] = {}  # conn_id -> recent silent frames
_vad_last_keepalive: dict[str, float] = {}  # conn_id -> silence_ms at last keepalive


def _pcm_frame_ms(pcm_bytes: bytes, rate: int = 16000) -> float:
    return len(pcm_bytes) / 2 / rate * 1000.0


def _pcm_rms(pcm_bytes: bytes) -> float:
    # 空帧或奇数长度帧（16bit 采样不允许奇数）直接按静音处理，避免
    # array("h") 抛 ValueError 冒泡到主循环断掉整个语音连接。
    if not pcm_bytes or len(pcm_bytes) % 2:
        return 0.0
    samples = array.array("h", pcm_bytes)
    if not samples:
        return 0.0
    sum_sq = 0.0
    for s in samples:
        sum_sq += s * s
    return math.sqrt(sum_sq / len(samples))


def unblock_voice_tts(thread_id: str) -> None:
    """Expose helper to unblock streaming TTS audio bytes immediately when text synthesis starts."""
    _is_sending_chat_tts_text[thread_id] = False


async def voice_receive_loop(
    websocket: WebSocket,
    volc_client: VolcAsrClient,
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
                logger.info(
                    f"[voice-ws] Volcengine connection closed for thread {thread_id} ({mode})"
                )
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
                        len(payload) if isinstance(payload, bytes | bytearray) else 0,
                        flag,
                    )
                    if isinstance(payload, bytes):
                        if flag:
                            continue

                        try:
                            await websocket.send_bytes(payload)
                        except Exception as e:
                            logger.warning(
                                f"[voice-ws] Failed to send audio bytes to Rust: {e}"
                            )
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
                                        MessageType.VOICE_PARTIAL,
                                        {"thread_id": thread_id, "text": asr_text},
                                    )
                                )
                            except Exception:
                                logger.debug(
                                    "[voice-ws] failed to send ASR partial for %s",
                                    thread_id,
                                    exc_info=True,
                                )

                # --- Fork: event 459 ASR done ---
                if event == 459:
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
                                        MessageType.VOICE_PARTIAL,
                                        {"thread_id": thread_id, "text": asr_text},
                                    )
                                )
                            except Exception:
                                logger.debug(
                                    "[voice-ws] failed to send ASR done partial for %s",
                                    thread_id,
                                    exc_info=True,
                                )
                            _is_sending_chat_tts_text[thread_id] = True
                            asyncio.create_task(run_agent_pipeline(websocket, thread_id, asr_text))
                        else:
                            # ASR 专用链路：最终定案由 voice.stop 的收集流程统一触发，
                            # 这里仅保留最新文本（服务端负包后仍可能返回剩余结果）。
                            if asr_text:
                                _last_asr_text[thread_id] = asr_text

                # --- Dialogue-only: event 359 TTS play ended ---
                elif event == 359 and mode == "dialogue":
                    _is_sending_chat_tts_text[thread_id] = False
                    await voice_state_machine.set(
                        thread_id, VoiceSessionState.LISTENING
                    )
                    try:
                        await websocket.send_json(
                            _envelope(
                                MessageType.VOICE_STATE,
                                {"state": "listening", "thread_id": thread_id},
                            )
                        )
                    except Exception:
                        logger.debug(
                            "[voice-ws] failed to send listening state for %s",
                            thread_id,
                            exc_info=True,
                        )

                # --- Dialogue-only: event 550/559 ChatTTSText ack ---
                elif event in (550, 559) and mode == "dialogue":
                    if event == 559:
                        logger.debug(
                            "[voice-ws] Event %s for thread %s", event, thread_id
                        )

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
                        asyncio.create_task(
                            run_agent_pipeline(websocket, thread_id, asr_text)
                        )
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
                    logger.debug(
                        "[voice-ws] failed to forward volc error for %s",
                        thread_id,
                        exc_info=True,
                    )
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
            _asr_audio_log.pop(thread_id, None)


async def _finalize_asr_session(
    websocket: WebSocket,
    volc_client: VolcAsrClient,
    thread_id: str,
    conn_id: str,
    mode: str = "dictation",
) -> None:
    """结束 ASR 会话：发负包定案，收集剩余增量结果。

    mode="dialogue" → 走 Agent（run_agent_pipeline）
    mode="dictation" → 走听写润色（_handle_dictation_finalize）

    调用方必须已停止 voice_receive_loop（否则并发 recv 会冲突），且客户端未 close。
    服务端负包后仍需 1-2s 处理已入队音频，故采用 3s 静默窗口收集。
    """
    try:
        await volc_client.finish()
    except Exception:
        logger.debug("[voice-ws] ASR finish failed for %s", thread_id, exc_info=True)
    final_text = _last_asr_text.pop(thread_id, "") or ""
    try:
        while True:
            try:
                resp = await asyncio.wait_for(volc_client.receive_response(), timeout=3)
            except asyncio.TimeoutError:
                break
            except (websockets.exceptions.ConnectionClosed, RuntimeError):
                break
            extra = (resp.get("payload_msg") or {}).get("extra") or {}
            text = (extra.get("origin_text") or "").strip()
            if text:
                final_text = text
    except Exception:
        logger.debug("[voice-ws] ASR collect failed for %s", thread_id, exc_info=True)
    if final_text:
        logger.info(f"[voice-ws] ASR session finished ({mode}): {final_text}")
        await manager.bind_thread(thread_id, conn_id)
        if mode == "dialogue":
            # 先注册 TTS 出口再起 Agent 任务，避免 early ACK 时 bridge 尚未就位
            await _register_dialogue_tts_bridge(thread_id, conn_id, websocket)
            asyncio.create_task(run_agent_pipeline(websocket, thread_id, final_text))
        else:
            asyncio.create_task(
                _handle_dictation_finalize(
                    {
                        "raw_text": final_text,
                        "thread_id": thread_id,
                        "target_locale": "zh",
                    },
                    conn_id,
                )
            )


async def _reconnect_asr_session(
    websocket: WebSocket,
    old_client: VolcAsrClient,
    thread_id: str,
    conn_id: str,
    mode: str = "dictation",
) -> tuple[VolcAsrClient | None, asyncio.Task | None]:
    """Close the finished ASR segment's client and start a fresh one.

    bigmodel_async closes the connection after the negative packet, so a new
    VolcAsrClient + voice_receive_loop must be created for the next segment.
    Returns (None, None) if reconnect fails (session ended).
    """
    from app.core.voice.executor import active_volc_clients

    try:
        await old_client.close()
    except Exception:
        logger.debug(
            "[voice-ws] ASR close failed on auto-segment for %s",
            thread_id,
            exc_info=True,
        )

    app_id = SystemConfigService.get_value("SEEDUPLEX_APP_ID")
    access_key = SystemConfigService.get_value("SEEDUPLEX_ACCESS_KEY")
    if not app_id or not access_key:
        logger.warning(
            "[voice-ws] Volcengine app_id/access_key missing on auto-segment reconnect"
        )
        await _notify_asr_session_dead(websocket)
        return None, None

    gen = _volc_gen.get(thread_id, 0) + 1
    _volc_gen[thread_id] = gen
    new_client = VolcAsrClient(app_id, access_key)
    try:
        await new_client.connect()
        if mode == "dictation":
            active_volc_clients[thread_id] = new_client
        else:
            await _register_dialogue_tts_bridge(thread_id, conn_id, websocket)
        task = asyncio.create_task(
            voice_receive_loop(
                websocket,
                new_client,
                thread_id,
                conn_id,
                mode,
                gen=gen,
            )
        )
        logger.info("[voice-ws] ASR auto-segment reconnected for thread %s", thread_id)
        return new_client, task
    except Exception as e:
        logger.exception(
            "[voice-ws] ASR auto-segment reconnect failed for %s: %s", thread_id, e
        )
        try:
            await new_client.close()
        except Exception:
            logger.debug(
                "[voice-ws] ASR reconnect close failed for %s", thread_id, exc_info=True
            )
        await _notify_asr_session_dead(websocket)
        return None, None


async def _notify_asr_session_dead(websocket: WebSocket) -> None:
    """Tell the Rust client the dictation ASR connection is gone.

    Rust forwards `system.error` as `voice:error` (frontend toast), so the
    user knows the session died instead of audio being dropped silently.
    """
    try:
        await websocket.send_json(
            _envelope(
                MessageType.SYSTEM_ERROR,
                {
                    "code": "asr_session_dead",
                    "message": "听写连接已断开，请关闭后重新开启听写",
                },
            )
        )
    except Exception:
        logger.debug("[voice-ws] failed to notify ASR session dead", exc_info=True)


async def run_agent_pipeline(websocket: WebSocket, thread_id: str, text: str) -> None:
    from app.core.channel.input.voice_input import voice_input
    from app.core.engine.worker_registry import worker_registry

    await _ensure_voice_input()

    from app.core.identity import identity_service
    from app.core.state import shared_state

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
                    _envelope(
                        MessageType.VOICE_STATE,
                        {"state": "processing", "thread_id": thread_id},
                    )
                )
            except Exception:
                logger.debug(
                    "[voice-ws] failed to send processing state for %s",
                    thread_id,
                    exc_info=True,
                )

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
    from app.core.state import shared_state

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
    logger.info(
        "[voice] client connected: %s (sent %d config keys, %d state keys)",
        conn_id,
        len(configs),
        len(state),
    )

    volc_client: VolcAsrClient | None = None
    volc_receive_task: asyncio.Task | None = None
    active_threads: set[str] = set()

    try:
        while True:
            # Receive raw message frame (supports both text/JSON and binary bytes)
            raw_msg = await websocket.receive()

            # Handle WebSocket disconnect message (Starlette may return this
            # as a dict instead of raising WebSocketDisconnect in some edge cases)
            if raw_msg.get("type") == "websocket.disconnect":
                logger.info(
                    "[voice-ws] received disconnect message, code=%s",
                    raw_msg.get("code"),
                )
                break

            # 1. Binary audio frame from Rust (microphone PCM)
            if "bytes" in raw_msg:
                pcm_bytes = raw_msg["bytes"]
                if volc_client:
                    if isinstance(volc_client, VolcAsrClient):
                        thread_id = _conn_thread.get(conn_id, "")
                        rms = _pcm_rms(pcm_bytes)
                        frame_ms = _pcm_frame_ms(pcm_bytes)
                        seg_mode = session_modes.get(thread_id, "dialogue")

                        if _vad_state.get(conn_id) == _VAD_STATE_SPEAKING:
                            # Throttled diagnostic: log ~once per second of audio
                            audio_log_bytes = _asr_audio_log.get(conn_id, 0)
                            if audio_log_bytes == 0:
                                logger.info(
                                    "[voice-ws] ASR audio frames arriving, first=%d bytes",
                                    len(pcm_bytes),
                                )
                            audio_log_bytes += len(pcm_bytes)
                            _asr_audio_log[conn_id] = audio_log_bytes
                            if audio_log_bytes >= 32000:
                                logger.info(
                                    "[voice-ws] ASR audio received %d bytes total",
                                    audio_log_bytes,
                                )
                                _asr_audio_log[conn_id] = 0

                            # Auto-segmentation: track silence; once the user has
                            # paused long enough with pending ASR text, finalize the
                            # current segment and reconnect for the next one. If the
                            # pause drags on WITHOUT pending text, drop back to the
                            # gated preroll state instead of billing more silence.
                            silence_ms = _dict_silence_ms.get(conn_id, 0.0)
                            if rms < _DICT_SILENCE_RMS:
                                silence_ms += frame_ms
                                if (
                                    silence_ms >= _DICT_AUTO_SEGMENT_MS
                                    and not _last_asr_text.get(thread_id)
                                ):
                                    logger.info(
                                        "[voice-ws] ASR trailing silence %.0fms with no text, gating again for %s",
                                        silence_ms,
                                        thread_id,
                                    )
                                    _dict_silence_ms[conn_id] = 0.0
                                    _vad_last_keepalive[conn_id] = 0.0
                                    _vad_state[conn_id] = _VAD_STATE_PREROLL
                                    _vad_preroll.setdefault(
                                        conn_id, deque(maxlen=_VAD_PREROLL_FRAMES)
                                    ).clear()
                            else:
                                silence_ms = 0.0
                            _dict_silence_ms[conn_id] = silence_ms

                            await volc_client.send_audio(pcm_bytes)
                            if (
                                thread_id
                                and silence_ms >= _DICT_AUTO_SEGMENT_MS
                                and _last_asr_text.get(thread_id)
                            ):
                                _dict_silence_ms[conn_id] = 0.0
                                _vad_last_keepalive[conn_id] = 0.0
                                logger.info(
                                    "[voice-ws] ASR auto-segment: silence %.0fms, finalizing segment for %s",
                                    silence_ms,
                                    thread_id,
                                )
                                # Stop the receive loop so the sync collection in
                                # _finalize_asr_session is the only WS consumer.
                                if volc_receive_task:
                                    volc_receive_task.cancel()
                                    try:
                                        await volc_receive_task
                                    except asyncio.CancelledError:
                                        pass
                                    volc_receive_task = None
                                await _finalize_asr_session(
                                    websocket, volc_client, thread_id, conn_id, seg_mode
                                )
                                (
                                    volc_client,
                                    volc_receive_task,
                                ) = await _reconnect_asr_session(
                                    websocket, volc_client, thread_id, conn_id, seg_mode
                                )
                                _vad_state[conn_id] = _VAD_STATE_PREROLL
                                _vad_preroll.setdefault(
                                    conn_id, deque(maxlen=_VAD_PREROLL_FRAMES)
                                ).clear()
                        else:
                            # Gated: preroll. Nobody is speaking, so do NOT send
                            # silence frames to Volc (billed by audio duration).
                            # Keep a short pre-roll ring so the speech onset is
                            # not clipped when speech is detected.
                            pre = _vad_preroll.setdefault(
                                conn_id, deque(maxlen=_VAD_PREROLL_FRAMES)
                            )
                            silence_ms = _dict_silence_ms.get(conn_id, 0.0)
                            if rms >= _DICT_SILENCE_RMS:
                                # Local barge-in: the user started speaking
                                # while the agent's TTS is still playing.
                                # (Volc ASR has no barge-in event; this is the
                                # app-side detection — cancel_thread is a no-op
                                # when no TTS segment is active.)
                                if seg_mode == "dialogue" and await voice_state_machine.get(thread_id) == VoiceSessionState.SPEAKING:
                                    logger.info("[voice-ws] local barge-in for %s (speech during SPEAKING)", thread_id)
                                    await _handle_barge_in(thread_id)
                                # Speech onset: flush the pre-roll + this frame.
                                audio_log_bytes = _asr_audio_log.get(conn_id, 0)
                                if audio_log_bytes == 0:
                                    logger.info("[voice-ws] ASR audio frames arriving, first=%d bytes", len(pcm_bytes))
                                audio_log_bytes += len(pcm_bytes)
                                _asr_audio_log[conn_id] = audio_log_bytes
                                if audio_log_bytes >= 32000:
                                    logger.info("[voice-ws] ASR audio received %d bytes total", audio_log_bytes)
                                    _asr_audio_log[conn_id] = 0
                                for buffered in list(pre):
                                    await volc_client.send_audio(buffered)
                                await volc_client.send_audio(pcm_bytes)
                                pre.clear()
                                _dict_silence_ms[conn_id] = 0.0
                                _vad_last_keepalive[conn_id] = 0.0
                                _vad_state[conn_id] = _VAD_STATE_SPEAKING
                            else:
                                pre.append(pcm_bytes)
                                silence_ms += frame_ms
                                _dict_silence_ms[conn_id] = silence_ms
                                # Keepalive: bigmodel_async ends the session if no
                                # packet arrives within 8s. Send a tiny silence
                                # frame every few seconds while gated — billed as
                                # ~0.7% of realtime duration instead of 100%.
                                last_keepalive = _vad_last_keepalive.get(conn_id, 0.0)
                                if silence_ms - last_keepalive >= _VAD_KEEPALIVE_INTERVAL_MS:
                                    _vad_last_keepalive[conn_id] = silence_ms
                                    await volc_client.send_audio(b"\x00\x00" * 320)
                                # Long idle window with no speech: refresh the ASR
                                # connection as belt-and-suspenders against any
                                # server-side session limits.
                                if thread_id and silence_ms >= _VAD_IDLE_RECONNECT_MS:
                                    _dict_silence_ms[conn_id] = 0.0
                                    _vad_last_keepalive[conn_id] = 0.0
                                    logger.info(
                                        "[voice-ws] ASR idle %.0fms, refreshing session for %s",
                                        silence_ms,
                                        thread_id,
                                    )
                                    if volc_receive_task:
                                        volc_receive_task.cancel()
                                        try:
                                            await volc_receive_task
                                        except asyncio.CancelledError:
                                            pass
                                        volc_receive_task = None
                                    await _finalize_asr_session(
                                        websocket,
                                        volc_client,
                                        thread_id,
                                        conn_id,
                                        seg_mode,
                                    )
                                    (
                                        volc_client,
                                        volc_receive_task,
                                    ) = await _reconnect_asr_session(
                                        websocket,
                                        volc_client,
                                        thread_id,
                                        conn_id,
                                        seg_mode,
                                    )
                                    pre.clear()
                    else:
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
                    await voice_state_machine.force_set(
                        thread_id, VoiceSessionState.IDLE
                    )
                    _is_sending_chat_tts_text.pop(thread_id, None)
                    _last_asr_text.pop(thread_id, None)
                    _asr_audio_log.pop(thread_id, None)
                    logger.info("[voice] cancel for thread %s", thread_id)
            elif mtype in (MessageType.VOICE_BARGE_IN, "voice.barge_in"):
                thread_id = str(body.get("thread_id", "")).strip()
                if thread_id:
                    await asyncio.create_task(_handle_barge_in(thread_id))
            elif mtype in (MessageType.VOICE_START,):
                thread_id = str(body.get("thread_id", "")).strip()
                if not thread_id:
                    continue
                await manager.bind_thread(thread_id, conn_id)
                VoiceChannel.reset_thread(thread_id)
                if not await voice_state_machine.can_accept_route(thread_id):
                    await _handle_barge_in(thread_id)

                # Store session mode early so the receive loop knows how to behave
                # Cache the previous session's mode BEFORE overwriting: the old
                # session (if any) is finalized below and must keep its own mode.
                prev_mode = session_modes.get(thread_id)
                mode = str(body.get("mode", "dialogue")).strip()
                session_modes[thread_id] = mode
                _conn_thread[conn_id] = thread_id
                _dict_silence_ms.pop(conn_id, None)
                _vad_state.pop(conn_id, None)
                _vad_preroll.pop(conn_id, None)
                _vad_last_keepalive.pop(conn_id, None)
                logger.info(
                    f"[voice-ws] Starting session for thread {thread_id} in {mode} mode"
                )

                app_id = SystemConfigService.get_value("SEEDUPLEX_APP_ID")
                access_key = SystemConfigService.get_value("SEEDUPLEX_ACCESS_KEY")
                if not app_id or not access_key:
                    logger.warning(
                        "[voice-ws] Volcengine app_id/access_key not configured"
                    )
                    await voice_state_machine.force_set(
                        thread_id, VoiceSessionState.IDLE
                    )
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
                            MessageType.VOICE_STATE,
                            {"state": "idle", "thread_id": thread_id},
                        )
                    )
                    continue

                # Cancel the old receive task BEFORE closing the client,
                # so the task gets CancelledError (clean exit) rather than
                # waking up to find self.ws is None (RuntimeError → websocket.close).
                if volc_receive_task:
                    volc_receive_task.cancel()
                    try:
                        await volc_receive_task
                    except asyncio.CancelledError:
                        pass
                    volc_receive_task = None
                if volc_client:
                    # 上个会话如果是 ASR 客户端（对话/听写），先定案定稿
                    if (
                        isinstance(volc_client, VolcAsrClient)
                        and volc_client.ws is not None
                    ):
                        await _finalize_asr_session(
                            websocket,
                            volc_client,
                            thread_id,
                            conn_id,
                            prev_mode or "dialogue",
                        )
                    await volc_client.close()
                    volc_client = None

                from app.core.voice.executor import active_volc_clients

                # Bump generation so any stale voice_receive_loop's
                # finally won't touch the state machine.
                gen = _volc_gen.get(thread_id, 0) + 1
                _volc_gen[thread_id] = gen
                # 三段式传输：ASR(VolcAsrClient) + TTS(VolcTtsClient)，替代实时对话 VolcDialogClient
                volc_client = VolcAsrClient(app_id, access_key)
                try:
                    await volc_client.connect()
                    if mode == "dictation":
                        active_volc_clients[thread_id] = volc_client
                    else:
                        await _register_dialogue_tts_bridge(
                            thread_id, conn_id, websocket
                        )
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
                    logger.info(
                        f"[voice-ws] Connected Volc ASR for thread {thread_id} in {mode} mode"
                    )

                    # Only announce "listening" after Volcengine is actually ready.
                    await voice_state_machine.set(
                        thread_id, VoiceSessionState.LISTENING
                    )
                    active_threads.add(thread_id)
                    await websocket.send_json(
                        _envelope(
                            MessageType.VOICE_STATE,
                            {"state": "listening", "thread_id": thread_id},
                        )
                    )
                except Exception as e:
                    logger.exception("[voice-ws] Volc client connect failed: %s", e)
                    await voice_state_machine.force_set(
                        thread_id, VoiceSessionState.IDLE
                    )
                    await websocket.send_json(
                        _envelope(
                            MessageType.SYSTEM_ERROR,
                            {"code": "volc_connect_failed", "message": str(e)},
                        )
                    )
                    await websocket.send_json(
                        _envelope(
                            MessageType.VOICE_STATE,
                            {"state": "idle", "thread_id": thread_id},
                        )
                    )
            elif mtype in (MessageType.VOICE_STOP,):
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
                    # Capture the session mode BEFORE popping it: _finalize_asr_session
                    # must know whether this was dictation (paste/polish) or dialogue
                    # (agent). Reading after the pop would always yield "dialogue".
                    mode = session_modes.get(thread_id, "dialogue")
                    session_modes.pop(thread_id, None)

                    # dictation: send the final (negative) packet so the ASR
                    # service returns the definitive result, then collect the
                    # remaining incremental results (the service needs a moment
                    # to process queued audio) with a silent 3s window before
                    # finalizing.
                    if (
                        isinstance(volc_client, VolcAsrClient)
                        and volc_client.ws is not None
                    ):
                        # Stop the receive loop first so the sync collection
                        # below is the only consumer of the websocket.
                        if volc_receive_task:
                            volc_receive_task.cancel()
                            try:
                                await volc_receive_task
                            except asyncio.CancelledError:
                                pass
                            volc_receive_task = None
                        await _finalize_asr_session(
                            websocket,
                            volc_client,
                            thread_id,
                            conn_id,
                            mode,
                        )
                    else:
                        if volc_receive_task:
                            volc_receive_task.cancel()
                            volc_receive_task = None

                    _last_asr_text.pop(thread_id, None)
                    _is_sending_chat_tts_text.pop(thread_id, None)
                    _asr_audio_log.pop(thread_id, None)
                    _volc_gen.pop(thread_id, None)
                    _dict_silence_ms.pop(conn_id, None)
                    _conn_thread.pop(conn_id, None)
                    _vad_state.pop(conn_id, None)
                    _vad_preroll.pop(conn_id, None)
                    _vad_last_keepalive.pop(conn_id, None)

                    # Clean up Volcengine client
                    from app.core.voice.executor import active_volc_clients

                    _tts = active_volc_clients.pop(thread_id, None)
                    if isinstance(_tts, VoiceTtsBridge):
                        await _tts.close()
                    if volc_client:
                        await volc_client.close()
                        volc_client = None

                    try:
                        await websocket.send_json(
                            _envelope(
                                MessageType.VOICE_STATE,
                                {"state": "idle", "thread_id": thread_id},
                            )
                        )
                    except Exception:
                        logger.debug(
                            "[voice-ws] failed to send idle state on stop for %s",
                            thread_id,
                            exc_info=True,
                        )
            elif mtype in (
                MessageType.VOICE_DICTATION_FINALIZE,
                "voice.dictation.finalize",
            ):
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
    except Exception as exc:
        logger.exception("[voice] connection error: %s", exc)
    finally:
        # Clean up Volcengine clients and tasks
        if volc_client:
            try:
                await volc_client.close()
            except Exception:
                logger.debug(
                    "[voice-ws] volc_client.close() raised, ignoring", exc_info=True
                )
        if volc_receive_task:
            volc_receive_task.cancel()
        from app.core.routing.conversation_state import (
            clear_thread_intent_state_for_threads,
        )  # noqa: I001
        from app.core.voice.executor import active_volc_clients  # noqa: I001

        # Only clear per-thread global state if this connection still owns it.
        # A Rust reconnect may have already started a new connection for the
        # same thread_id; in that case the new connection is responsible for
        # cleaning up and we must not destroy its active Volcengine client or
        # wipe conversation intent state.
        threads_to_clear_intent: list[str] = []
        for tid in active_threads:
            cur = active_volc_clients.get(tid)
            if volc_client is not None and cur is volc_client:
                active_volc_clients.pop(tid, None)
            elif isinstance(cur, VoiceTtsBridge) and cur.conn_id == conn_id:
                active_volc_clients.pop(tid, None)
                await cur.close()
            if not await manager.is_thread_bound(tid):
                session_modes.pop(tid, None)
                threads_to_clear_intent.append(tid)
                _last_asr_text.pop(tid, None)
                _is_sending_chat_tts_text.pop(tid, None)
                _asr_audio_log.pop(tid, None)
                _volc_gen.pop(tid, None)
        _dict_silence_ms.pop(conn_id, None)
        _conn_thread.pop(conn_id, None)
        _vad_state.pop(conn_id, None)
        _vad_preroll.pop(conn_id, None)
        _vad_last_keepalive.pop(conn_id, None)
        if threads_to_clear_intent:
            clear_thread_intent_state_for_threads(threads_to_clear_intent)
        await manager.unregister(conn_id)
