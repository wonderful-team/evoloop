"""Voice executor — pushes TTS tokens and results to the voice WebSocket.

Used by VoiceChannel (agent TTS streaming) to push tokens and boundaries
back through the voice WS for real-time playback. Also provides voice task
cancellation and registry helpers for voice route handling.
"""

import logging
from typing import Any

from app.core.engine.worker_registry import worker_registry
from app.core.routing.routing_data import get_store
from app.core.voice.state_machine import VoiceSessionState, voice_state_machine

logger = logging.getLogger(__name__)

_routing_store = get_store()

# Manager set at application startup by voice_ws.py
manager: Any = None
envelope_fn: Any = None
message_type: Any = None

# Voice thread registry: thread_ids currently in voice mode mapped to their
# source (e.g. "agent"). MessagePublisher and VoiceChannel use membership checks
# to decide whether to route messages to the voice channel (WS). Thread_ids are
# added by _mark_voice and removed by consume_voice.
_voice_registry: dict[str, str] = {}

# Active Volcengine Dialogue WS Clients
active_volc_clients: dict[str, Any] = {}


async def cancel_voice_task(thread_id: str) -> bool:
    """Cancel the current voice task for a thread via worker_registry.

    Returns True if a task was found and cancelled, False otherwise.
    """
    return await worker_registry.cancel_worker(thread_id)


async def _mark_voice(thread_id: str, source: str) -> None:
    """Mark a thread as being handled by voice from the given source."""
    _voice_registry[thread_id] = source


async def consume_voice(thread_id: str) -> None:
    """Consume/clear the voice state for a thread (post-cleanup)."""
    _voice_registry.pop(thread_id, None)


async def push_voice_result(
    thread_id: str, status: str, summary: str, *, skip_tts: bool = False
) -> None:
    """Push a voice route result (done/failed/routed) to the voice WS."""
    if manager is None:
        logger.warning("[voice-exec] manager not set, cannot push result")
        return
    body = {"thread_id": thread_id, "status": status, "summary": summary}
    if envelope_fn and message_type:
        env = envelope_fn(message_type.VOICE_ROUTE_RESULT, body)
        await manager.push(
            thread_id, env.model_dump() if hasattr(env, "model_dump") else env
        )
    else:
        await manager.push(thread_id, body)

    # Synthesize TTS for non-empty summaries in done status
    if summary and status == "done" and not skip_tts:
        await push_tts_text(thread_id, summary)


async def push_voice_token(thread_id: str, token: str, _index: int) -> None:
    """Push a streaming TTS token for real-time playback."""
    if manager is None:
        return
    body = {"thread_id": thread_id, "token": token}
    if envelope_fn and message_type:
        env = envelope_fn(message_type.VOICE_TOKEN, body)
        await manager.push(
            thread_id, env.model_dump() if hasattr(env, "model_dump") else env
        )
    else:
        await manager.push(thread_id, body)


async def push_voice_tts_boundary(thread_id: str, sentence: str, index: int) -> None:
    """Push a TTS sentence boundary for real-time playback."""
    if manager is None:
        return
    body = {"thread_id": thread_id, "sentence": sentence, "index": index}
    if envelope_fn and message_type:
        env = envelope_fn(message_type.VOICE_TTS_BOUNDARY, body)
        await manager.push(
            thread_id, env.model_dump() if hasattr(env, "model_dump") else env
        )
    else:
        await manager.push(thread_id, body)


async def push_tts_text(thread_id: str, text: str) -> None:
    """推文本给 Volcengine 对话 session 合成 TTS 音频。"""
    client = active_volc_clients.get(thread_id)
    if not client:
        return
    if client.ws is None:
        try:
            await client.reconnect()
        except Exception as e:
            logger.error("[voice-exec] push_tts_text reconnect failed: %s", e)
            return
    try:
        from app.api.routes.voice_ws import unblock_voice_tts
        unblock_voice_tts(thread_id)
    except ImportError:
        pass

    try:
        await client.send_chat_tts_text(start=True, end=False, content=text)
        await client.send_chat_tts_text(start=False, end=True, content="")
        logger.info(
            "[voice-exec] push_tts_text sent %d chars to thread %s",
            len(text),
            thread_id,
        )
    except Exception as exc:
        logger.error("[voice-exec] push_tts_text failed: %s", exc)


# ── 宏执行 ──────────────────────────────


async def maybe_push_tts(thread_id: str, text: str) -> None:
    """推确认语——统一走 push_tts_text，和安抚话术同一路径。"""
    await push_tts_text(thread_id, text)


async def _set_idle_if_needed(thread_id: str) -> None:
    """Transition the voice state machine back to IDLE, avoiding no-op warnings."""
    current = await voice_state_machine.get(thread_id)
    if current != VoiceSessionState.IDLE:
        await voice_state_machine.set(thread_id, VoiceSessionState.IDLE)


async def push_macro_result(thread_id: str, status: str, summary: str) -> None:
    """推 voice.route_result，复用 Rust 现有的 done/failed/cancelled 处理分支。"""
    if manager is None:
        logger.warning("[voice-exec] manager not set, cannot push macro result")
        return
    body = {"thread_id": thread_id, "status": status, "summary": summary}
    if envelope_fn and message_type:
        env = envelope_fn(message_type.VOICE_ROUTE_RESULT, body)
        await manager.push(
            thread_id, env.model_dump() if hasattr(env, "model_dump") else env
        )
    else:
        await manager.push(thread_id, body)
    await _set_idle_if_needed(thread_id)


async def handle_navigate(route: str, thread_id: str, feedback: str | None = None) -> None:
    """Send a frontend navigation command via WS."""
    logger.info("[voice-exec] handle_navigate route=%s thread=%s feedback=%s", route, thread_id, feedback)
    if manager is None:
        logger.warning("[voice-exec] manager not set, cannot push navigate")
        return
    if feedback is None:
        feedback = _routing_store.builtin_responses.get("generic", {}).get("ok", "")
    body = {"route": route, "thread_id": thread_id, "feedback": feedback}
    if envelope_fn and message_type:
        env = envelope_fn("voice.navigate", body)
        await manager.push(
            thread_id,
            env.model_dump() if hasattr(env, "model_dump") else env,
        )
    else:
        await manager.push(thread_id, body)
    await maybe_push_tts(thread_id, feedback)
    await _set_idle_if_needed(thread_id)


async def push_local_result(thread_id: str, action: str, args: Any) -> None:
    """Push an L0 local result back to the voice WS."""
    if manager is None:
        logger.warning("[voice-exec] manager not set, cannot push local result")
        return
    body = {
        "thread_id": thread_id,
        "status": "routed",
        "target": {"type": "local", "action": action},
        "params": args or {},
        "candidates": [],
    }
    if envelope_fn and message_type:
        env = envelope_fn(message_type.VOICE_ROUTE_RESULT, body)
        await manager.push(
            thread_id, env.model_dump() if hasattr(env, "model_dump") else env
        )
    else:
        await manager.push(thread_id, body)
    await _set_idle_if_needed(thread_id)
    logger.info("[voice-exec] L0 local action: %s for thread %s", action, thread_id)


async def _load_skill(skill_id: Any) -> Any:
    """Load a LearnedSkill row by primary key."""
    try:
        from app.infrastructure.database import session_scope
        from app.models.learning import LearnedSkill

        async with session_scope() as session:
            return await session.get(LearnedSkill, skill_id)
    except Exception as exc:
        logger.warning("[voice-exec] failed to load skill %s: %s", skill_id, exc)
        return None


def _missing_skill_params(parameters: Any, params: dict[str, Any]) -> list[str]:
    """Return the names of required skill parameters missing from ``params``."""
    import json

    if isinstance(parameters, str):
        try:
            parameters = json.loads(parameters)
        except Exception:
            parameters = []
    if not isinstance(parameters, list):
        return []
    return [
        p["name"]
        for p in parameters
        if isinstance(p, dict) and p.get("required") and p.get("name") not in params
    ]


async def _resolve_skill_to_macro(skill_id: Any) -> int | None:
    """Find the macro paired with a learned skill via ``fallback_skill_id``."""
    try:
        from sqlalchemy import select

        from app.infrastructure.database import session_scope
        from app.models.macro import Macro

        async with session_scope() as session:
            stmt = select(Macro.id).where(Macro.fallback_skill_id == skill_id).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    except Exception as exc:
        logger.warning(
            "[voice-exec] failed to resolve skill %s to macro: %s", skill_id, exc
        )
        return None
