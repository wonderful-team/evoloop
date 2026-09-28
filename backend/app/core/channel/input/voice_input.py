"""VoiceInputChannel — normalizes voice.route messages from the local voice WS.

The L0/L1 routing decision logic has moved to the shared dispatcher in
``app.core.routing.dispatch_handler``.  This channel is now responsible only
for normalizing inbound voice.route payloads into ``IncomingMessage``.

2026-08 (parent-run-liveness): post-dispatch run registration and task
finalization (``post_dispatch`` / ``await_and_finalize`` / ``handle_cancelled``)
moved into ``AgentSession``; this channel only normalizes input. ``receive``
injects the ``has_running_worker`` 元数据键（客户端 wire 契约）from the
AgentRunRegistry（会话外后台执行）。
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.channel.base import IncomingMessage, InputChannel
from app.core.identity import identity_service
from app.core.state import shared_state

logger = logging.getLogger(__name__)


class VoiceInputChannel(InputChannel):
    """Voice input: receives ASR text from the local voice WebSocket."""

    name = "voice"

    def __init__(self) -> None:
        self._run_registry: Any = None

    def bind(
        self,
        executor: Any,
        state_machine: Any,
        state_enum: Any,
        agent_run_registry: Any,
    ) -> None:
        """Inject runtime dependencies from voice_ws.py (kept for compat; agent_run_registry used)."""
        _ = (executor, state_machine, state_enum)
        self._run_registry = agent_run_registry

    async def receive(self, raw: dict[str, Any], **kwargs: Any) -> IncomingMessage | None:
        """Normalize an inbound voice.route message into ``IncomingMessage``.

        Returns ``None`` when the payload is not a valid chat message (e.g. a
        control signal or empty text).  L0 routing is handled by the shared
        dispatcher, not here.
        """
        text = str(raw.get("text", "")).strip()
        thread_id = str(raw.get("thread_id", "")).strip()
        if not text or not thread_id:
            return None

        project_id = int(raw.get("project_id", 0))
        if not project_id:
            project_id = await shared_state.get_active_project_id()
        message_id = raw.get("message_id")
        member_id = int(raw.get("member_id", 0)) or kwargs.get("member_id", 0)
        if not member_id:
            member_id = await identity_service.get_member_id() or 0

        meta: dict[str, Any] = {"source": "voice", "voice_thread_id": thread_id}
        await self._inject_has_running_worker(thread_id, meta, raw)

        return IncomingMessage(
            source="voice",
            thread_id=thread_id,
            text=text,
            project_id=project_id,
            member_id=member_id,
            metadata=meta,
            message_id=message_id,
        )

    async def _inject_has_running_worker(self, thread_id: str, meta: dict[str, Any], raw: dict[str, Any]) -> None:
        """has_running_worker 数据源：运行中 agent 注册表（AgentRunRegistry）。"""
        if self._run_registry is not None:
            running_worker = await self._run_registry.get_run(thread_id)
            if running_worker and running_worker.status == "running":
                meta["has_running_worker"] = "true"
                meta["running_worker_desc"] = running_worker.description


voice_input = VoiceInputChannel()
