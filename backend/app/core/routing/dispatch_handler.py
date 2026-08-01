"""Unified dispatcher for chat and voice routes.

This module consolidates the previously duplicated routing logic in
``app.api.routes.agent._chat`` and ``app.api.routes.voice_ws``:

1. Normalize raw input into an ``IncomingMessage`` via an ``InputChannel``.
2. Run ``CommandRouter.resolve`` to get a ``RouteDecision``.
3. Keep the ``intent_hint`` as a Pydantic object on the message metadata.
4. Dispatch any L0 hit through ``dispatch_decision`` + a channel presenter.
5. For L0 misses, return the normalized message and the ``dispatch_agent_run``
   inputs so the caller can start the agent background worker in the
   channel-appropriate way (HTTP ``BackgroundTasks`` for web,
   ``asyncio.create_task`` for voice).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.core.channel.base import IncomingMessage, InputChannel
from app.core.context import EvoContext
from app.core.routing.channels.dispatch import RoutePresenter, dispatch_decision
from app.core.routing.command_router import CommandRouter
from app.core.routing.thread_locks import route_lock_scope

logger = logging.getLogger(__name__)

command_router = CommandRouter()


@dataclass
class DispatchOutcome:
    """Outcome of a unified route dispatch attempt.

    - ``handled=True``: an L0/local route resolved the request. For the web
      channel ``local_response`` holds the JSON payload; for voice it is
      ``None`` because the result was already pushed to the WebSocket.
    - ``handled=False``: the request must be delegated to the agent.
      ``msg`` is the normalized ``IncomingMessage`` and ``inputs`` is the
      value returned by ``InputChannel.dispatch`` (the agent run inputs).
    """

    handled: bool
    local_response: Any = None
    msg: IncomingMessage | None = None
    inputs: Any = None


async def dispatch_user_message(
    raw: dict[str, Any],
    *,
    source: str,
    input_channel: InputChannel,
    presenter: RoutePresenter,
    thread_id: str,
    project_id: int,
    member_id: int,
    context: EvoContext,
    worker_registry: Any = None,
) -> DispatchOutcome:
    """Normalize, route, and dispatch a user message from any channel.

    The caller is responsible for holding the route lock and setting an active
    ``EvoContext`` (use ``route_lock_scope``).  This function performs the
    channel-agnostic work that was previously duplicated across chat and voice.
    """
    msg = await input_channel.receive(raw, context=context, member_id=member_id)
    if msg is None:
        return DispatchOutcome(handled=False, msg=None)

    if not msg.source:
        msg.source = source
    if msg.project_id is None:
        msg.project_id = project_id
    if msg.member_id is None:
        msg.member_id = member_id

    decision = await command_router.resolve(
        msg.text,
        thread_id=thread_id,
        project_id=project_id,
        source=source,
    )

    if decision.intent_hint:
        msg.metadata = msg.metadata or {}
        msg.metadata["intent_hint"] = decision.intent_hint

    local_result = await dispatch_decision(
        decision,
        presenter,
        thread_id=thread_id,
        project_id=project_id,
        worker_registry=worker_registry,
    )

    if local_result.handled:
        logger.info(
            "[dispatch] %s L0 handled for thread %s (target=%s)",
            source,
            thread_id,
            decision.target_type,
        )
        return DispatchOutcome(handled=True, local_response=local_result.payload)

    logger.info(
        "[dispatch] %s L0 miss for thread %s (intent=%s) → agent",
        source,
        thread_id,
        decision.intent_hint,
    )
    inputs = await input_channel.dispatch(msg)
    return DispatchOutcome(handled=False, msg=msg, inputs=inputs)


__all__ = [
    "DispatchOutcome",
    "dispatch_user_message",
    "route_lock_scope",
    "command_router",
]
