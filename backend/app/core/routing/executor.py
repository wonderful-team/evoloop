"""Voice executor — pushes TTS tokens and results to the voice WebSocket.

Used by VoiceChannel (agent TTS streaming) to push tokens and boundaries
back through the voice WS for real-time playback. Also provides per-thread
locking and task cancellation for voice route handling.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Manager set at application startup by voice_ws.py
manager: Any = None
envelope_fn: Any = None
message_type: Any = None

# Per-thread async locks for route serialization
_thread_locks: dict[str, asyncio.Lock] = {}

# Per-thread voice source tracking
_voice_sources: dict[str, str] = {}

# Active Volcengine Dialogue WS Clients
active_volc_clients: dict[str, Any] = {}

# Voice thread registry: set of thread_ids currently in voice mode.
# MessagePublisher checks this to decide whether to route messages to
# the voice channel (WS). Thread_ids are added by _mark_voice and
# removed by consume_voice.
_voice_registry: set[str] = set()


async def get_thread_lock(thread_id: str) -> asyncio.Lock:
    """Get or create a per-thread async lock for route serialization."""
    if thread_id not in _thread_locks:
        _thread_locks[thread_id] = asyncio.Lock()
    return _thread_locks[thread_id]


def clear_tts_discard_flag(thread_id: str) -> None:
    """Allow agent TTS audio frames to reach Rust (stop discarding auto-response)."""
    from app.api.routes.voice_ws import _is_sending_chat_tts_text
    _is_sending_chat_tts_text[thread_id] = False


async def cancel_voice_task(thread_id: str) -> bool:
    """Cancel the current voice task for a thread via worker_registry.

    Returns True if a task was found and cancelled, False otherwise.
    """
    from app.core.engine.worker_registry import worker_registry

    return await worker_registry.cancel_worker(thread_id)


async def _mark_voice(thread_id: str, source: str) -> None:
    """Mark a thread as being handled by voice from the given source."""
    _voice_sources[thread_id] = source
    _voice_registry.add(thread_id)


async def consume_voice(thread_id: str) -> None:
    """Consume/clear the voice state for a thread (post-cleanup)."""
    _voice_sources.pop(thread_id, None)
    _voice_registry.discard(thread_id)


async def push_voice_result(thread_id: str, status: str, summary: str) -> None:
    """Push a voice route result (done/failed/routed) to the voice WS."""
    if manager is None:
        logger.warning("[voice-exec] manager not set, cannot push result")
        return
    body = {"thread_id": thread_id, "status": status, "summary": summary}
    if envelope_fn and message_type:
        env = envelope_fn(message_type.VOICE_ROUTE_RESULT, body)
        await manager.push(thread_id, env)
    else:
        await manager.push(thread_id, body)

    # Synthesize TTS for non-empty summaries in done status
    if summary and status == "done":
        await push_tts_text(thread_id, summary)


async def push_voice_token(thread_id: str, token: str, _index: int) -> None:
    """Push a streaming TTS token for real-time playback."""
    if manager is None:
        return
    body = {"thread_id": thread_id, "token": token}
    if envelope_fn and message_type:
        env = envelope_fn(message_type.VOICE_TOKEN, body)
        await manager.push(thread_id, env)
    else:
        await manager.push(thread_id, body)


async def push_voice_tts_boundary(thread_id: str, sentence: str, index: int) -> None:
    """Push a TTS sentence boundary for real-time playback."""
    if manager is None:
        return
    body = {"thread_id": thread_id, "sentence": sentence, "index": index}
    if envelope_fn and message_type:
        env = envelope_fn(message_type.VOICE_TTS_BOUNDARY, body)
        await manager.push(thread_id, env)
    else:
        await manager.push(thread_id, body)


async def push_tts_text(thread_id: str, text: str) -> None:
    """推文本给 Volcengine 对话 session 合成 TTS 音频（AB mode: 全量文本 + 空结束标记）。"""
    client = active_volc_clients.get(thread_id)
    if client:
        try:
            logger.info(
                "[voice-exec] push_tts_text start=True,end=False content=[%d chars] head=%r tail=%r",
                len(text), text[:100], text[-100:] if len(text) > 100 else ""
            )
            await client.send_chat_tts_text(start=True, end=False, content=text)
            await client.send_chat_tts_text(start=False, end=True, content="")
            logger.info("[voice-exec] push_tts_text sent %d chars to thread %s", len(text), thread_id)
        except Exception as exc:
            logger.error("[voice-exec] push_tts_text failed: %s", exc)
    else:
        logger.warning("[voice-exec] push_tts_text: no active volc client for thread %s", thread_id)

