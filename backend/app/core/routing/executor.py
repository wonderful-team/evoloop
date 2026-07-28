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
    """推文本给 Volcengine 对话 session 合成 TTS 音频。"""
    client = active_volc_clients.get(thread_id)
    if not client:
        logger.warning("[voice-exec] push_tts_text: no active volc client for thread %s", thread_id)
        return
    if client.ws is None:
        logger.warning("[voice-exec] push_tts_text: ws closed, reconnecting...")
        try:
            await client.reconnect()
        except Exception as e:
            logger.error("[voice-exec] push_tts_text reconnect failed: %s", e)
            return
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


# ── 宏执行（从 voice_input.py 移入） ──────────────────────────────

from app.core.voice.state_machine import voice_state_machine, VoiceSessionState

_MACRO_TIMEOUT = 3.0

NAV_FEEDBACK: dict[str, str] = {
    "/chat": "已回到主界面",
    "/projects": "已打开项目管理",
    "/todos": "已打开待办事项",
    "/learning": "已进入学习中心",
    "/settings": "已打开设置",
    "/subscription": "已打开订阅管理",
    "/login": "已打开登录页",
    "/chat?new=true": "已创建新对话",
    "/learning?tab=android": "已打开手机桌面",
    "/learning?tab=macros": "已进入技能录制",
    "__HIDE_WINDOW__": "已隐藏主界面",
}


async def maybe_push_tts(thread_id: str, text: str) -> None:
    """推确认语——统一走 push_tts_text，和安抚话术同一路径。"""
    await push_tts_text(thread_id, text)


async def push_macro_result(thread_id: str, status: str, summary: str) -> None:
    """推 voice.route_result，复用 Rust 现有的 done/failed/cancelled 处理分支。"""
    body = {"thread_id": thread_id, "status": status, "summary": summary}
    await manager.push(
        thread_id, envelope_fn(message_type.VOICE_ROUTE_RESULT, body)
    )
    await voice_state_machine.set(thread_id, VoiceSessionState.IDLE)


async def handle_navigate(route: str, thread_id: str) -> None:
    """Send a frontend navigation command via WS."""
    feedback = NAV_FEEDBACK.get(route, "好的")
    body = {"route": route, "thread_id": thread_id, "feedback": feedback}
    await manager.push(
        thread_id,
        envelope_fn("voice.navigate", body),
    )
    await maybe_push_tts(thread_id, feedback)
    await voice_state_machine.set(thread_id, VoiceSessionState.IDLE)


async def push_local_result(thread_id: str, action: str, args: Any) -> None:
    """Push an L0 local result back to the voice WS."""
    body = {
        "thread_id": thread_id,
        "status": "routed",
        "target": {"type": "local", "action": action},
        "params": args or {},
        "candidates": [],
    }
    await manager.push(
        thread_id, envelope_fn(message_type.VOICE_ROUTE_RESULT, body)
    )
    await voice_state_machine.set(thread_id, VoiceSessionState.IDLE)
    logger.info("[voice-exec] L0 local action: %s for thread %s", action, thread_id)


async def dispatch_macro(
    thread_id: str, macro_id: int, args: dict, project_id: int,
    worker_registry: Any = None,
) -> bool:
    """加载 Macro → preflight → run_deterministic → 推 done/failed/cancelled + 确认语。

    Returns True 宏执行成功，False 执行失败（可由 Agent 兜底）。
    """
    from app.core.execution.macro.runner import (
        VOICE_POLICY, MacroGateError, load_macro, preflight, run_deterministic,
    )

    await voice_state_machine.set(thread_id, VoiceSessionState.SPEAKING)

    macro = await load_macro(macro_id)
    if macro is None:
        await push_macro_result(thread_id, "failed", "未找到该宏")
        return False
    try:
        script = preflight(macro, args)
    except MacroGateError as e:
        await push_macro_result(thread_id, "failed", e.message)
        return False

    async def _run():
        return await run_deterministic(
            macro, thread_id=thread_id, params=args, project_id=project_id,
            script=script, policy=VOICE_POLICY,
            skip_activity_log=True,
            skip_recording=True,
        )

    task = asyncio.create_task(_run())
    if worker_registry is not None:
        await worker_registry.register_worker(thread_id, task, description=f"macro:{macro_id}")

    try:
        outcome = await asyncio.wait_for(task, timeout=_MACRO_TIMEOUT)
    except asyncio.TimeoutError:
        await push_macro_result(thread_id, "failed", "执行超时")
        await maybe_push_tts(thread_id, "执行超时")
        return False
    except asyncio.CancelledError:
        await push_macro_result(thread_id, "cancelled", "已取消")
        raise

    ok = outcome.ok
    status = "done" if ok else "failed"
    summary = outcome.message or ("完成" if ok else "执行失败")
    logger.info("[voice-exec] dispatch_macro: push_result thread=%s status=%s summary=%r", thread_id, status, summary)
    await push_macro_result(thread_id, status, summary)
    if ok:
        await maybe_push_tts(thread_id, summary)
    return ok


async def handle_builtin(
    thread_id: str, action: str, args: dict,
    worker_registry: Any = None,
) -> bool:
    """处理 Evoloop 内置命令。Returns True 成功，False 失败（Agent 兜底）。"""
    if action == "ack":
        logger.info("[voice-exec] ack for thread %s (no-op)", thread_id)
        await push_local_result(thread_id, action, args)
        await maybe_push_tts(thread_id, "好的")
        return True
    elif action == "cancel":
        if worker_registry is not None:
            cancelled = await worker_registry.cancel_worker(thread_id)
            if cancelled:
                await push_macro_result(thread_id, "cancelled", "已取消")
                logger.info("[voice-exec] cancel: worker cancelled for thread %s", thread_id)
                return True
        await push_macro_result(thread_id, "done", "没有正在执行的任务")
        await maybe_push_tts(thread_id, "没有正在执行的任务")
        logger.info("[voice-exec] cancel: no running worker for thread %s", thread_id)
        return True
    elif action == "rename":
        from app.core.shared_state import shared_state
        name = args.get("name", "")
        if name:
            await shared_state.set("agent_name", name)
            logger.info("[voice-exec] rename to %s for thread %s", name, thread_id)
        await push_local_result(thread_id, action, args)
        await maybe_push_tts(thread_id, f"好的，以后叫我{name}" if name else "好的")
        return True
    else:
        await push_local_result(thread_id, action, args)
        await maybe_push_tts(thread_id, "好的")
        return True

