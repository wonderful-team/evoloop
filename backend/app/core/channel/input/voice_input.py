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

import yaml

from app.constants import DEFAULT_PROJECT_ID
from app.core.channel.base import IncomingMessage, InputChannel
from app.core.identity import identity_service
from app.core.routing.executor import push_tts_text
from app.core.routing.init_spec import _TEMPLATES
from app.core.routing.intent_classifier import predict as classifier_predict
from app.core.routing.router import get_local_matcher
from app.core.shared_state import shared_state
from app.infrastructure.database import session_scope
from app.models.macro import Macro
from sqlmodel import select

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

    # ── Compound command decompose ────────────────────────────
    _CONJUNCTIONS_PATH = None  # override for custom path

    @classmethod
    def _get_conjunctions(cls) -> tuple[str, ...]:
        """Read conjunctions from data/conjunctions.txt.

        Falls back to built-in list if file is unavailable.
        File format: one conjunction per line, # comments and blank lines ignored.
        """
        path = cls._CONJUNCTIONS_PATH
        if path is None:
            from pathlib import Path
            path = Path(__file__).resolve().parent.parent.parent.parent.parent / "data" / "conjunctions.txt"

        try:
            with open(path, encoding="utf-8") as f:
                result = []
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        result.append(stripped)
            if result:
                return tuple(result)
        except (FileNotFoundError, OSError, PermissionError):
            pass

        return ("然后", "并且", "而且", "同时", "接着", "再然后")

    @staticmethod
    def _decompose(text: str) -> list[str]:
        """Split compound command at conjunctions. Returns [text] if no conjunction found."""
        import re
        conjunctions = VoiceInputChannel._get_conjunctions()
        pattern = "|".join(re.escape(c) for c in conjunctions)
        parts = re.split(pattern, text)
        parts = [p.strip() for p in parts if p.strip()]
        return parts if len(parts) > 1 else [text]

    async def _process_single(
        self, text: str, thread_id: str, project_id: int
    ) -> bool:
        """Run L0 on a single sub-command. Returns True if handled locally, False if it needs Agent."""
        intent_name, margin = classifier_predict(text)
        l0_match = None
        if intent_name and margin >= 0.08:
            l0_match = await self._resolve_intent(intent_name, text, thread_id, project_id)
        if l0_match is None:
            matcher = await get_local_matcher()
            l0_match = matcher.match(text)
        if l0_match is not None:
            action, args = l0_match
            if action.startswith("macro:"):
                macro_id = int(action.split(":", 1)[1])
                await self._dispatch_macro(thread_id, macro_id, args, project_id)
            else:
                await self._handle_builtin(thread_id, action, args)
            return True
        return False

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
        member_id = int(raw.get("member_id", 0))
        if not member_id:
            member_id = await identity_service.get_member_id() or 0
        # Try compound command decomposition first
        sub_commands = self._decompose(text)
        if len(sub_commands) > 1:
            all_handled = True
            for sub in sub_commands:
                if not await self._process_single(sub, thread_id, project_id):
                    all_handled = False
                    break
            if all_handled:
                return None
            # Fall through to Agent with original text if any sub-command missed

        # Single command path (or compound fallback to Agent)
        if len(sub_commands) == 1:
            handled = await self._process_single(text, thread_id, project_id)
            if handled:
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
            member_id=member_id,
            metadata=meta,
            message_id=message_id,
        )

    async def dispatch(self, msg: IncomingMessage) -> Any:
        """Submit to agent engine, with voice-specific side effects."""
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

        from app.core.engine.background_agent import run_agent_background  # noqa: TID252

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
        if self._state_machine is not None:
            await self._state_machine.set(thread_id, self._state_enum.LISTENING)

    # ── L0 Macro dispatch ──────────────────────────────────────

    async def _resolve_intent(self, intent_name: str, text: str, thread_id: str, project_id: int) -> tuple[str, dict] | None:
        """Resolve BERT intent_name to an L0 action. Returns (action, args) or None."""
        import re

        # Intent-specific guards to reject false positives
        if intent_name == "报时" and not re.search(r"几[号点时]|星期|时间|日期|报时", text):
            return None
        if intent_name in ("打开应用", "切换到应用", "退出应用") and not re.search(
            r"(打开|启动|开一下|切换到|去|退出|关闭|关掉)\w", text
        ):
            return None

        # Device name redirect: text contains WiFi/蓝牙 → map to correct intent
        _device_intents = {
            "WiFi": ["打开_WiFi", "关闭_WiFi", "打开 WiFi", "关闭 WiFi"],
            "蓝牙": ["打开蓝牙", "关闭蓝牙"],
            "蓝牙设备": ["连接蓝牙设备", "断开蓝牙设备"],
        }
        for keyword, targets in _device_intents.items():
            if keyword in text and intent_name in ("打开应用", "打开_WiFi", "打开信息",
                                                    "退出应用", "关闭_WiFi",
                                                    "切换到应用"):
                candidates = targets
                break
        else:
            # Normalize: YAML keys may have underscores where DB names have spaces
            candidates = [intent_name, intent_name.replace("_", " ")]

        async with session_scope() as session:
            for name in candidates:
                stmt = select(Macro).where(Macro.name == name, Macro.status == "verified")
                result = await session.execute(stmt)
                macro = result.scalar_one_or_none()
                if macro:
                    return f"macro:{macro.id}", self._extract_slots(intent_name, text)

        # 2. Try builtin — lookup from init_spec._TEMPLATES
        for tmpl in _TEMPLATES:
            if intent_name == tmpl["action"]:
                return tmpl["action"], {"name": text} if tmpl["action"] == "rename" else {}
        # Also try matching by Chinese name (from training data labels)
        _BUILTIN_ALIASES = {"取消": "cancel", "结束": "end", "重说": "clarify", "改名": "rename"}
        if intent_name in _BUILTIN_ALIASES:
            action = _BUILTIN_ALIASES[intent_name]
            return action, {"name": text} if action == "rename" else {}

        return None

    def _extract_slots(self, intent_name: str, text: str) -> dict:
        """Simple slot extraction from raw text."""
        # For slotted macros, extract the parameter from the command suffix
        prefixes = ["打开", "启动", "关闭", "退出", "切换到", "去", "搜索", "搜一下"]
        for p in prefixes:
            if text.startswith(p):
                return {"_value": text[len(p):].strip(), "_text": text}
        return {}

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
            await self._maybe_push_tts(thread_id, "执行超时")
            return
        except asyncio.CancelledError:
            await self._push_macro_result(thread_id, "cancelled", "已取消")
            raise

        status = "done" if outcome.ok else "failed"
        summary = outcome.message or ("完成" if outcome.ok else "执行失败")
        await self._push_macro_result(thread_id, status, summary)
        await self._maybe_push_tts(thread_id, summary)

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
            await self._maybe_push_tts(thread_id, "好的")
        elif action == "cancel":
            if self._worker_registry is not None:
                cancelled = await self._worker_registry.cancel_worker(thread_id)
                if cancelled:
                    await self._push_macro_result(thread_id, "cancelled", "已取消")
                    logger.info("[voice-input] cancel: worker cancelled for thread %s", thread_id)
                    return
            await self._push_macro_result(thread_id, "done", "没有正在执行的任务")
            await self._maybe_push_tts(thread_id, "没有正在执行的任务")
            logger.info("[voice-input] cancel: no running worker for thread %s", thread_id)
        elif action == "rename":
            name = args.get("name", "")
            if name:
                await shared_state.set("agent_name", name)
                logger.info("[voice-input] rename to %s for thread %s", name, thread_id)
            await self._push_local_result(thread_id, action, args)
            await self._maybe_push_tts(thread_id, f"好的，以后叫我{name}" if name else "好的")
        else:
            # end / clarify
            await self._push_local_result(thread_id, action, args)
            await self._maybe_push_tts(thread_id, "好的")

    async def _maybe_push_tts(self, thread_id: str, text: str) -> None:
        """推确认语（L0 匹配后的短确认）给 Volcengine 合成 TTS。

        L0 builtin/macro 执行完成后，通过此方法将确认语文本推给 Volcengine 合成语音。
        """
        await push_tts_text(thread_id, text)

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
