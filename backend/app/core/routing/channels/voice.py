"""Voice router — thin adapter from L0 decisions to voice-specific execution.

The matching/decision logic lives in ``app.core.routing.command_router``.  This
module only cares about how to present a routed decision to the voice client:
TTS, WebSocket pushes, and the voice state machine.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.routing.channels.dispatch import DispatchResult, dispatch_decision
from app.core.routing.command_router import CommandRouter
from app.core.routing.executor import (
    handle_navigate,
    maybe_push_tts,
    push_local_result,
    push_macro_result,
)
from app.core.routing.routing_data import get_store

logger = logging.getLogger(__name__)

_routing_store = get_store()


class VoicePresenter:
    """Present L0 routing decisions to the voice channel via WebSocket + TTS."""

    source = "voice"
    macro_timeout = 3.0

    def __init__(self, thread_id: str) -> None:
        self._thread_id = thread_id

    async def on_agent(self, _decision: Any) -> DispatchResult:
        return DispatchResult(handled=False)

    async def on_local(
        self,
        _decision: Any,
        action: str,
        args: dict[str, Any],
        route: str | None,
    ) -> DispatchResult:
        if route is not None:
            await handle_navigate(route, self._thread_id)
            return DispatchResult(handled=True)
        await push_local_result(self._thread_id, action, args)
        await maybe_push_tts(
            self._thread_id, _routing_store.builtin_responses["local"]["success"]
        )
        return DispatchResult(handled=True)

    async def on_builtin(
        self,
        _decision: Any,
        action: str,
        _args: dict[str, Any],
        outcome: Any,
    ) -> DispatchResult:
        status = "done" if outcome.ok else "failed"
        if action == "cancel" and outcome.data.get("cancelled"):
            status = "cancelled"
        await push_macro_result(self._thread_id, status, outcome.message)
        if outcome.ok:
            await maybe_push_tts(self._thread_id, outcome.message)
        return DispatchResult(handled=outcome.ok)

    async def on_macro(
        self,
        _decision: Any,
        _macro_id: int,
        _args: dict[str, Any],
        outcome: Any,
    ) -> DispatchResult:
        if outcome.action_type == "navigate":
            await handle_navigate(outcome.data["route"], self._thread_id)
            return DispatchResult(handled=True)
        status = "done" if outcome.ok else "failed"
        await push_macro_result(self._thread_id, status, outcome.message)
        if outcome.ok:
            await maybe_push_tts(self._thread_id, outcome.message)
        return DispatchResult(handled=outcome.ok)


async def execute_route_for_voice(
    text: str,
    *,
    thread_id: str,
    project_id: int,
    worker_registry: Any = None,
) -> bool:
    """Execute L0 routing for a single voice utterance and push the result.

    Returns ``True`` if the utterance was handled locally (L0 hit), ``False``
    if it should be delegated to the agent.  This is the low-level helper used
    by tests and any compound-command processing path.
    """
    decision = await CommandRouter().resolve(
        text,
        thread_id=thread_id,
        project_id=project_id,
        source="voice",
    )
    presenter = VoicePresenter(thread_id)
    result = await dispatch_decision(
        decision,
        presenter,
        thread_id=thread_id,
        project_id=project_id,
        worker_registry=worker_registry,
    )
    return result.handled


__all__ = ["VoicePresenter", "execute_route_for_voice"]
