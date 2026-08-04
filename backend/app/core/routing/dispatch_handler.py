"""Unified dispatcher for chat and voice routes.

This module consolidates the previously duplicated routing logic in
``app.api.routes.agent._chat`` and ``app.api.routes.voice_ws``:

1. Normalize raw input into an ``IncomingMessage`` via an ``InputChannel``.
2. Run ``CommandRouter.resolve`` to get a ``RouteDecision``.
3. Store the ``intent_hint`` as a JSON-safe dict on the message metadata
   (the metadata is persisted before the engine hydrates it).
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
from app.core.routing.actions import ActionOutcome, run_builtin, run_macro
from app.core.routing.command_router import CommandRouter
from app.core.routing.routing_data import get_store
from app.core.routing.schemas import IntentHint
from app.core.routing.thread_locks import route_lock_scope

logger = logging.getLogger(__name__)

command_router = CommandRouter()
_routing_store = get_store()


@dataclass
class DispatchOutcome:
    """Outcome of a unified route dispatch attempt.

    - ``handled=True``: an L0/local route resolved the request.
      ``local_response`` holds the ``ActionOutcome`` containing the execution details.
    - ``handled=False``: the request must be delegated to the agent.
      ``msg`` is the normalized ``IncomingMessage`` and ``inputs`` is the
      value returned by ``InputChannel.dispatch`` (the agent run inputs).
    """

    handled: bool
    local_response: ActionOutcome | None = None
    msg: IncomingMessage | None = None
    inputs: Any = None


async def dispatch_user_message(
    raw: dict[str, Any],
    *,
    source: str,
    input_channel: InputChannel,
    thread_id: str,
    project_id: int,
    member_id: int,
    context: EvoContext,
    worker_registry: Any = None,
) -> DispatchOutcome:
    """Normalize, route, and dispatch a user message from any channel.

    The caller is responsible for holding the route lock and setting an active
    ``EvoContext`` (use ``route_lock_scope``). This function performs the
    channel-agnostic routing work.
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
        # The metadata dict is persisted to JSON before the engine hydrates it,
        # so keep the intent hint as a plain dict to avoid serialization errors.
        msg.metadata["intent_hint"] = (
            decision.intent_hint.model_dump()
            if isinstance(decision.intent_hint, IntentHint)
            else decision.intent_hint
        )

    target_type = decision.target_type

    if target_type == "agent":
        logger.info(
            "[dispatch] %s L0 miss for thread %s (intent=%s) → agent",
            source,
            thread_id,
            decision.intent_hint,
        )
        inputs = await input_channel.dispatch(msg)
        return DispatchOutcome(handled=False, msg=msg, inputs=inputs)

    if target_type == "local":
        action = decision.target.get("action", "")
        args = decision.params
        route = (
            decision.target.get("route")
            if decision.target.get("type") == "navigate"
            else None
        )
        if route is not None:
            local_outcome = ActionOutcome(
                ok=True,
                message=_routing_store.builtin_responses["generic"]["ok"],
                action_type="navigate",
                data={"route": route},
            )
            logger.info("[dispatch] %s L0 navigate handled for thread %s", source, thread_id)
            return DispatchOutcome(handled=True, local_response=local_outcome)
        else:
            if source == "voice":
                local_outcome = ActionOutcome(
                    ok=True,
                    message=_routing_store.builtin_responses["local"]["success"],
                    action_type="local",
                    data={"action": action, "args": args},
                )
                logger.info("[dispatch] %s L0 local action handled for thread %s", source, thread_id)
                return DispatchOutcome(handled=True, local_response=local_outcome)
            else:
                logger.info("[dispatch] web local non-navigate action delegates to agent")
                inputs = await input_channel.dispatch(msg)
                return DispatchOutcome(handled=False, msg=msg, inputs=inputs)

    if target_type == "builtin":
        action = decision.target.get("action", "")
        args = decision.params
        outcome = await run_builtin(
            action,
            args,
            thread_id=thread_id,
            worker_registry=worker_registry,
        )
        handled = True
        if source == "voice" and not outcome.ok:
            handled = False
        logger.info(
            "[dispatch] %s L0 builtin handled=%s for thread %s",
            source,
            handled,
            thread_id,
        )
        if handled:
            return DispatchOutcome(handled=True, local_response=outcome)
        else:
            inputs = await input_channel.dispatch(msg)
            return DispatchOutcome(handled=False, msg=msg, inputs=inputs)

    if target_type == "macro":
        macro_id = decision.target.get("id")
        if not isinstance(macro_id, int):
            logger.warning("[dispatch] macro decision missing id: %s", decision)
            inputs = await input_channel.dispatch(msg)
            return DispatchOutcome(handled=False, msg=msg, inputs=inputs)

        macro_timeout = 10.0 if source == "voice" else None
        outcome = await run_macro(
            macro_id,
            decision.params,
            thread_id=thread_id,
            project_id=project_id,
            source=source,
            timeout=macro_timeout,
            worker_registry=worker_registry,
        )
        handled = True
        if source == "voice" and outcome.action_type != "navigate" and not outcome.ok:
            handled = False

        if handled:
            return DispatchOutcome(handled=True, local_response=outcome)
        else:
            inputs = await input_channel.dispatch(msg)
            return DispatchOutcome(handled=False, msg=msg, inputs=inputs)

    logger.warning("[dispatch] unknown target_type: %s", target_type)
    inputs = await input_channel.dispatch(msg)
    return DispatchOutcome(handled=False, msg=msg, inputs=inputs)


__all__ = [
    "DispatchOutcome",
    "dispatch_user_message",
    "route_lock_scope",
    "command_router",
]
