"""
VoiceInputChannel — receives voice.route messages from the local voice WS.

Owns the full voice route lifecycle:
1. L0 matching (builtin + Macro)
2. IncomingMessage construction (for agent dispatch)
3. L0 local result push (when matched)
4. Dispatch result handling (worker registration, error/cancelled push)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.channel.base import IncomingMessage, InputChannel
from app.constants import DEFAULT_PROJECT_ID

logger = logging.getLogger(__name__)

_MACRO_TIMEOUT = 3.0


class VoiceInputChannel(InputChannel):
    """Voice input: receives ASR text from the local voice WebSocket."""

    name = "voice"

    def __init__(self) -> None:
        self._manager: Any = None
        self._executor: Any = None
        self._state_machine: Any = None
        self._worker_registry: Any = None
        self._envelope: Any = None
        self._message_type: Any = None

    def bind(
        self,
        manager: Any,
        executor: Any,
        state_machine: Any,
        state_enum: Any,
        worker_registry: Any,
        envelope_fn: Any,
        message_type: Any,
    ) -> None:
        """Inject runtime dependencies from voice_ws.py."""
        self._manager = manager
        self._executor = executor
        self._state_machine = state_machine
        self._state_enum = state_enum
        self._worker_registry = worker_registry
        self._envelope = envelope_fn
        self._message_type = message_type

    async def receive(self, raw: dict[str, Any], **kwargs: Any) -> IncomingMessage | None:
        """Process an inbound voice.route message.

        Returns an ``IncomingMessage`` when the route should be dispatched
        to the agent (L0 miss), or ``None`` when the route was handled
        locally (L0 hit / duplicate / invalid).
        """
        text = str(raw.get("text", "")).strip()
        thread_id = str(raw.get("thread_id", "")).strip()
        if not text or not thread_id:
            return None

        project_id = int(raw.get("project_id", DEFAULT_PROJECT_ID))
        message_id = raw.get("message_id")

        # L0 matching
        from app.core.routing.router import get_local_matcher

        matcher = await get_local_matcher()
        l0_match = matcher.match(text)

        if l0_match is not None:
            action, args = l0_match
            if action.startswith("macro:"):
                macro_id = int(action.split(":", 1)[1])
                await self._dispatch_macro(thread_id, macro_id, args, project_id)
            else:
                await self._handle_builtin(thread_id, action, args)
            return None

        # L0 miss — build IncomingMessage for agent
        running_worker = await self._worker_registry.get_worker(thread_id) if self._worker_registry else None
        meta = {"source": "voice", "voice_thread_id": thread_id}
        if running_worker and running_worker.status == "running":
            meta["has_running_worker"] = "true"
            meta["running_worker_desc"] = running_worker.description

        return IncomingMessage(
            source="voice",
            thread_id=thread_id,
            text=text,
            project_id=project_id,
            metadata=meta,
            message_id=message_id,
        )

    async def dispatch(self, msg: IncomingMessage) -> Any:
        """Submit to agent engine, with voice-specific side effects."""
        if self._state_machine is not None:
            await self._state_machine.set(msg.thread_id, self._state_enum.SPEAKING)
        if self._executor is not None:
            await self._executor._mark_voice(msg.thread_id, "agent")
        return await super().dispatch(msg)

    async def post_dispatch(self, msg: IncomingMessage, result: Any) -> dict[str, Any] | None:
        """Handle post-dispatch actions: register worker or push failure.

        Returns a dict with ``task`` key when the worker was created,
        or ``None`` on failure.
        """
        thread_id = msg.thread_id

        if result.status == "failed":
            await self._executor.consume_voice(thread_id)
            await self._executor.push_voice_result(
                thread_id, "failed", getattr(result, "error", "") or "dispatch failed"
            )
            return None

        from app.core.engine.background_agent import run_agent_background

        running_worker = await self._worker_registry.get_worker(thread_id) if self._worker_registry else None
        desc = running_worker.description if running_worker else ""

        task = asyncio.create_task(run_agent_background(thread_id, result.inputs))
        if self._worker_registry is not None:
            await self._worker_registry.register_worker(thread_id, task, description=desc)

        # Store the previous worker for post-dispatch re-registration
        return {"task": task, "old_worker_task": running_worker.task if running_worker and running_worker.status == "running" else None}

    async def await_and_finalize(
        self, thread_id: str, task: Any, old_worker_task: Any, worker_desc: str = ""
    ) -> None:
        """Await the agent task, then re-register old worker if it survived (SUPERVISOR_CHOOSE_QUERY)."""
        try:
            await task
        except asyncio.CancelledError:
            await self.handle_cancelled(thread_id)
        else:
            if old_worker_task is not None and not old_worker_task.done():
                await self._worker_registry.register_worker(thread_id, old_worker_task, description=worker_desc)

    async def handle_cancelled(self, thread_id: str) -> None:
        """Clean up when the agent task is cancelled."""
        await self._executor.consume_voice(thread_id)
        await self._executor.push_voice_result(thread_id, "cancelled", "")

    # ── L0 Macro dispatch ─────────────────────────────────────

    async def _dispatch_macro(self, thread_id: str, macro_id: int, args: dict, project_id: int) -> None:
        """加载 Macro → preflight → run_deterministic → 推 done/failed/cancelled。

        超时保护：5 秒上限，防止 osascript 阻塞。
        Barge-in：包装为 task 注册到 worker_registry，可被 cancel。
        """
        from app.core.execution.macro.runner import (
            VOICE_POLICY, MacroGateError, load_macro, preflight, run_deterministic,
        )

        if self._state_machine is not None:
            await self._state_machine.set(thread_id, self._state_enum.SPEAKING)

        macro = await load_macro(macro_id)
        if macro is None:
            await self._push_macro_result(thread_id, "failed", "未找到该宏")
            return
        try:
            script = preflight(macro, args)
        except MacroGateError as e:
            await self._push_macro_result(thread_id, "failed", e.message)
            return

        async def _run():
            return await run_deterministic(
                macro, thread_id=thread_id, params=args, project_id=project_id,
                script=script, policy=VOICE_POLICY,
                skip_activity_log=True,
                skip_recording=True,
            )

        task = asyncio.create_task(_run())
        if self._worker_registry is not None:
            await self._worker_registry.register_worker(thread_id, task, description=f"macro:{macro_id}")

        try:
            outcome = await asyncio.wait_for(task, timeout=_MACRO_TIMEOUT)
        except asyncio.TimeoutError:
            await self._push_macro_result(thread_id, "failed", "执行超时")
            return
        except asyncio.CancelledError:
            await self._push_macro_result(thread_id, "cancelled", "已取消")
            raise

        status = "done" if outcome.ok else "failed"
        summary = outcome.message or ("完成" if outcome.ok else "执行失败")
        await self._push_macro_result(thread_id, status, summary)

    async def _push_macro_result(self, thread_id: str, status: str, summary: str) -> None:
        """推 voice.route_result，复用 Rust 现有的 done/failed/cancelled 处理分支。"""
        body = {"thread_id": thread_id, "status": status, "summary": summary}
        await self._manager.push(
            thread_id, self._envelope(self._message_type.VOICE_ROUTE_RESULT, body)
        )
        await self._state_machine.set(thread_id, self._state_enum.IDLE)

    # ── L0 builtin commands ────────────────────────────────────

    async def _handle_builtin(self, thread_id: str, action: str, args: dict) -> None:
        """处理 Evoloop 内置命令。"""
        if action == "ack":
            logger.info("[voice-input] ack for thread %s (no-op)", thread_id)
            await self._push_local_result(thread_id, action, args)
        elif action == "cancel":
            if self._worker_registry is not None:
                cancelled = await self._worker_registry.cancel_worker(thread_id)
                if cancelled:
                    await self._push_macro_result(thread_id, "cancelled", "已取消")
                    logger.info("[voice-input] cancel: worker cancelled for thread %s", thread_id)
                    return
            await self._push_macro_result(thread_id, "done", "没有正在执行的任务")
            logger.info("[voice-input] cancel: no running worker for thread %s", thread_id)
        elif action == "rename":
            name = args.get("name", "")
            if name:
                from app.core.shared_state import shared_state
                await shared_state.set("agent_name", name)
                logger.info("[voice-input] rename to %s for thread %s", name, thread_id)
            await self._push_local_result(thread_id, action, args)
        else:
            # end / clarify
            await self._push_local_result(thread_id, action, args)

    async def _push_local_result(self, thread_id: str, action: str, args: Any) -> None:
        """Push an L0 local result back to the voice WS."""
        body = {
            "thread_id": thread_id,
            "status": "routed",
            "target": {"type": "local", "action": action},
            "params": args or {},
            "candidates": [],
        }
        await self._manager.push(
            thread_id, self._envelope(self._message_type.VOICE_ROUTE_RESULT, body)
        )
        await self._state_machine.set(thread_id, self._state_enum.IDLE)
        logger.info("[voice-input] L0 local action: %s for thread %s", action, thread_id)


voice_input = VoiceInputChannel()
