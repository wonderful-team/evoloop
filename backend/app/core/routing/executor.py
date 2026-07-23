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


async def consume_voice(thread_id: str) -> None:
    """Consume/clear the voice state for a thread (post-cleanup)."""
    _voice_sources.pop(thread_id, None)


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


async def push_voice_tts_boundary(thread_id: str, text: str, _index: int) -> None:
    """Push a TTS boundary (sentence boundary for streaming TTS)."""
    if manager is None:
        return
    body = {"thread_id": thread_id, "text": text}
    if envelope_fn and message_type:
        env = envelope_fn(message_type.VOICE_TTS_BOUNDARY, body)
        await manager.push(thread_id, env)
    else:
        await manager.push(thread_id, body)
