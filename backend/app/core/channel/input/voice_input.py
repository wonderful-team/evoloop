"""VoiceInputChannel — normalizes voice.route messages from the local voice WS.

The L0/L1 routing decision logic has moved to the shared dispatcher in
``app.core.routing.dispatch_handler``.  This channel is now responsible only
for:

1. Normalizing inbound voice.route payloads into ``IncomingMessage``.
2. Marking the thread as a voice agent dispatch.
3. Handing post-dispatch worker registration and task finalization.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.channel.base import IncomingMessage, InputChannel
from app.core.identity import identity_service

logger = logging.getLogger(__name__)


class VoiceInputChannel(InputChannel):
    """Voice input: receives ASR text from the local voice WebSocket."""

    name = "voice"

    def __init__(self) -> None:
        self._manager: Any = None
        self._executor: Any = None
        self._state_machine: Any = None
        self._state_enum: Any = None
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

    async def receive(
        self, raw: dict[str, Any], **kwargs: Any
    ) -> IncomingMessage | None:
        """Normalize an inbound voice.route message into ``IncomingMessage``.

        Returns ``None`` when the payload is not a valid chat message (e.g. a
        control signal or empty text).  L0 routing is handled by the shared
        dispatcher, not here.
        """
        text = str(raw.get("text", "")).strip()
        thread_id = str(raw.get("thread_id", "")).strip()
        if not text or not thread_id:
            return None

        project_id = int(raw.get("project_id", DEFAULT_PROJECT_ID))
        message_id = raw.get("message_id")
        member_id = int(raw.get("member_id", 0)) or kwargs.get("member_id", 0)
        if not member_id:
            member_id = await identity_service.get_member_id() or 0

        running_worker = (
            await self._worker_registry.get_worker(thread_id)
            if self._worker_registry
            else None
        )
        meta: dict[str, Any] = {"source": "voice", "voice_thread_id": thread_id}
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
        """Mark the thread as voice dispatch, then submit to the agent engine."""
        if self._executor is not None:
            await self._executor._mark_voice(msg.thread_id, "agent")
        return await super().dispatch(msg)

    async def post_dispatch(
        self, msg: IncomingMessage, result: Any
    ) -> dict[str, Any] | None:
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

        running_worker = (
            await self._worker_registry.get_worker(thread_id)
            if self._worker_registry
            else None
        )
        desc = running_worker.description if running_worker else ""

        task = asyncio.create_task(run_agent_background(thread_id, result.inputs))
        if self._worker_registry is not None:
            await self._worker_registry.register_worker(
                thread_id, task, description=desc
            )

        # Store the previous worker for post-dispatch re-registration
        return {
            "task": task,
            "old_worker_task": running_worker.task
            if running_worker and running_worker.status == "running"
            else None,
        }

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
                await self._worker_registry.register_worker(
                    thread_id, old_worker_task, description=worker_desc
                )

    async def handle_cancelled(self, thread_id: str) -> None:
        """Clean up when the agent task is cancelled."""
        await self._executor.consume_voice(thread_id)
        await self._executor.push_voice_result(thread_id, "cancelled", "")
        if self._state_machine is not None:
            await self._state_machine.set(thread_id, self._state_enum.LISTENING)


voice_input = VoiceInputChannel()
