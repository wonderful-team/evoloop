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
    if status == "done":
        if _tts_boundary_started.get(thread_id):
            client = active_volc_clients.get(thread_id)
            if client:
                try:
                    await client.send_chat_tts_text(start=False, end=True, content="")
                except Exception:
                    pass
        elif summary:
            await push_tts_text(thread_id, summary)



# Tracks whether push_voice_tts_boundary has been called for a thread (first=start)
_tts_boundary_started: dict[str, bool] = {}

async def push_voice_tts_boundary(thread_id: str, text: str, _index: int, start: bool | None = None, end: bool | None = None) -> None:
    """Push a TTS boundary (sentence boundary for streaming TTS) to active Volcengine client."""
    client = active_volc_clients.get(thread_id)
    if client:
        if start is None:
            start = not _tts_boundary_started.get(thread_id, False)
        if end is None:
            end = False
        logger.info("[voice-exec] Sending TTS boundary start=%s end=%s to Volcengine: %s", start, end, text)
        try:
            await client.send_chat_tts_text(start=start, end=end, content=text)
            _tts_boundary_started[thread_id] = True
        except Exception as exc:
            logger.error("[voice-exec] Failed to send TTS boundary: %s", exc)
    else:
        logger.warning("[voice-exec] No active Volcengine client for thread %s", thread_id)


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



async def push_tts_text(thread_id: str, text: str) -> None:
    """推文本给 Volcengine 对话 session 合成 TTS 音频。"""
    client = active_volc_clients.get(thread_id)
    if client:
        try:
            await client.send_chat_tts_text(start=True, end=False, content=text)
            await client.send_chat_tts_text(start=False, end=True, content="")
            logger.info("[voice-exec] push_tts_text sent %d chars to thread %s", len(text), thread_id)
        except Exception as exc:
            logger.error("[voice-exec] push_tts_text failed: %s", exc)
    else:
        logger.warning("[voice-exec] push_tts_text: no active volc client for thread %s", thread_id)

