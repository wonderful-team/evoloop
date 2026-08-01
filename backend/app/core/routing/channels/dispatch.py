"""Channel-agnostic dispatch core for L0 RouteDecision.

Both voice and web adapters share the same decision-to-action pipeline:

1. Resolve a ``RouteDecision`` from ``CommandRouter``.
2. For ``agent`` -> delegate.
3. For ``local`` -> handle navigation or push a local result.
4. For ``builtin`` -> ``actions.run_builtin`` + channel-specific presentation.
5. For ``macro`` -> ``actions.run_macro`` + channel-specific presentation.

The only differences are the **presentation layer** (TTS/WS vs JSON response)
and a few parameters (voice fast-fail timeout, web self-healing policy).  Those
are encapsulated in the ``RoutePresenter`` protocol.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.routing.actions import run_builtin, run_macro
from app.core.routing.schemas import RouteDecision

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    """Result of dispatching a ``RouteDecision`` to a channel presenter."""

    handled: bool
    payload: Any | None = None


class RoutePresenter(Protocol):
    """Channel-specific presentation callbacks for a routed decision."""

    source: str
    macro_timeout: float | None

    async def on_agent(self, decision: RouteDecision) -> DispatchResult:
        """Called when the decision is to delegate to the agent."""
        ...

    async def on_local(
        self,
        decision: RouteDecision,
        action: str,
        args: dict[str, Any],
        route: str | None,
    ) -> DispatchResult:
        """Called for a local action. ``route`` is set for navigate decisions."""
        ...

    async def on_builtin(
        self,
        decision: RouteDecision,
        action: str,
        args: dict[str, Any],
        outcome: Any,
    ) -> DispatchResult:
        """Called after a builtin action has been executed."""
        ...

    async def on_macro(
        self,
        decision: RouteDecision,
        macro_id: int,
        args: dict[str, Any],
        outcome: Any,
    ) -> DispatchResult:
        """Called after a macro has been executed."""
        ...


async def dispatch_decision(
    decision: RouteDecision,
    presenter: RoutePresenter,
    *,
    thread_id: str,
    project_id: int,
    worker_registry: Any | None = None,
) -> DispatchResult:
    """Execute a ``RouteDecision`` using the supplied channel presenter.

    Returns a ``DispatchResult`` where ``handled`` tells the caller whether the
    request was resolved locally (``True``) or should be delegated to the agent
    (``False``).  ``payload`` is presenter-specific: voice uses ``None`` while web
    uses the JSON response body.
    """
    target_type = decision.target_type

    if target_type == "agent":
        return await presenter.on_agent(decision)

    if target_type == "local":
        action = decision.target.get("action", "")
        args = decision.params
        route = (
            decision.target.get("route")
            if decision.target.get("type") == "navigate"
            else None
        )
        return await presenter.on_local(decision, action, args, route)

    if target_type == "builtin":
        action = decision.target.get("action", "")
        args = decision.params
        outcome = await run_builtin(
            action,
            args,
            thread_id=thread_id,
            worker_registry=worker_registry,
        )
        return await presenter.on_builtin(decision, action, args, outcome)

    if target_type == "macro":
        macro_id = decision.target.get("id")
        if not isinstance(macro_id, int):
            logger.warning("[dispatch] macro decision missing id: %s", decision)
            return DispatchResult(handled=False)
        outcome = await run_macro(
            macro_id,
            decision.params,
            thread_id=thread_id,
            project_id=project_id,
            source=presenter.source,
            timeout=presenter.macro_timeout,
            worker_registry=worker_registry,
        )
        return await presenter.on_macro(
            decision, macro_id, decision.params, outcome
        )

    logger.warning("[dispatch] unknown target_type: %s", target_type)
    return DispatchResult(handled=False)
