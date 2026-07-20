"""Voice task registry, streaming, and result pushback for voice channel.

All functions here serve the real-time voice dialogue path:
voice task registration/cancellation, token streaming, and result delivery.
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from typing import Any

from app.core.routing.connection import manager
from app.core.schemas.canonical import MessageType, create_envelope

logger = logging.getLogger(__name__)

# thread_id -> "skill" | "agent". Authoritative voice-source marker consumed by
# VoiceChannel to push the terminal result. In-memory only: a restart
# mid-run loses it, but the WS is gone too, so the client's 60s timeout covers
# it (§9.2).
_voice_registry: dict[str, str] = {}
_voice_lock = asyncio.Lock()

# message_id carrier for terminal-result caching of duplicate route requests.
_current_message_id: ContextVar[str | None] = ContextVar(
    "_current_message_id", default=None
)


async def _mark_voice(thread_id: str, kind: str) -> None:
    async with _voice_lock:
        _voice_registry[thread_id] = kind


async def consume_voice(thread_id: str) -> str | None:
    """Pop and return the voice-source kind for `thread_id` (finish.py hook)."""
    async with _voice_lock:
        return _voice_registry.pop(thread_id, None)


async def push_voice_result(thread_id: str, status: str, summary: str) -> None:
    body = {
        "thread_id": thread_id,
        "status": status,
        "summary": summary,
    }
    await manager.push(thread_id, create_envelope(
        MessageType.VOICE_ROUTE_RESULT, body
    ).model_dump())
    message_id = _current_message_id.get()
    if message_id:
        await manager.record_terminal_result(message_id, body)


# ---------------------------------------------------------------------------
# VoiceTaskRegistry — register / cancel active voice tasks per thread
# ---------------------------------------------------------------------------

_voice_tasks: dict[str, asyncio.Task[Any]] = {}
_voice_task_lock = asyncio.Lock()

# Per-thread locks to prevent overlapping route execution (barge-in safety).
_thread_locks: dict[str, asyncio.Lock] = {}
_thread_locks_lock = asyncio.Lock()


async def get_thread_lock(thread_id: str) -> asyncio.Lock:
    async with _thread_locks_lock:
        if thread_id not in _thread_locks:
            _thread_locks[thread_id] = asyncio.Lock()
        return _thread_locks[thread_id]


async def register_voice_task(thread_id: str, task: asyncio.Task[Any]) -> None:
    async with _voice_task_lock:
        old = _voice_tasks.get(thread_id)
        if old is not None and not old.done():
            old.cancel()
        _voice_tasks[thread_id] = task


async def cancel_voice_task(thread_id: str) -> bool:
    async with _voice_task_lock:
        task = _voice_tasks.pop(thread_id, None)
    if task is not None and not task.done():
        task.cancel()
        logger.info("[voice-executor] cancelled task for thread %s", thread_id)
        return True
    return False


# ---------------------------------------------------------------------------
# Streaming LLM output — token-by-token push via voice.token / voice.tts_boundary
# ---------------------------------------------------------------------------

_SENTENCE_BOUNDARIES = "。！？.!?\n…"


_EOS_TOKENS = ("</s>", "<|im_end|>", "<|endoftext|>")

async def push_voice_token(thread_id: str, token: str, index: int) -> None:
    for eos in _EOS_TOKENS:
        token = token.replace(eos, "")
    if not token:
        return
    await manager.push(thread_id, create_envelope(
        MessageType.VOICE_TOKEN,
        {"thread_id": thread_id, "token": token, "index": index},
    ).model_dump())


async def push_voice_tts_boundary(thread_id: str, sentence: str, index: int) -> None:
    await manager.push(thread_id, create_envelope(
        MessageType.VOICE_TTS_BOUNDARY,
        {"thread_id": thread_id, "sentence": sentence, "index": index},
    ).model_dump())


async def stream_llm_response(
    thread_id: str,
    messages: list[dict],
    model_name: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """Stream LLM output token-by-token, pushing voice.token and voice.tts_boundary.

    Returns the full accumulated text.
    Cancels gracefully if the task is cancelled (barge-in).
    """
    from app.infrastructure.llm.factory import LLMConfig, LLMFactory

    config = LLMConfig(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=True,
        base_url=base_url,
        api_key=api_key,
    )
    llm = await LLMFactory.create_llm(config)

    token_index = 0
    sentence_buf = ""
    full_text = ""

    try:
        async for chunk in llm.astream(messages, config={"callbacks": []}):
            token = getattr(chunk, "content", "") or ""
            if not token:
                continue
            full_text += token
            sentence_buf += token
            await push_voice_token(thread_id, token, token_index)
            token_index += 1

            if any(ch in _SENTENCE_BOUNDARIES for ch in token):
                stripped = sentence_buf.strip()
                if stripped:
                    await push_voice_tts_boundary(thread_id, stripped, token_index)
                sentence_buf = ""

        if sentence_buf.strip():
            await push_voice_tts_boundary(thread_id, sentence_buf.strip(), token_index)

    except asyncio.CancelledError:
        logger.info("[voice-executor] LLM stream cancelled for thread %s", thread_id)
        raise
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as exc:
        logger.error("[voice-executor] LLM stream failed: %s", exc)
        raise

    return full_text
