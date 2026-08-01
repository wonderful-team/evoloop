"""Web/chat adapter for L0 routed decisions.

Unlike the voice adapter, this does not speak TTS or drive a voice state
machine.  It executes macros/builtins synchronously in the HTTP request and
returns a response body the web client can render immediately.  Navigation
macros are returned as a ``navigate`` directive so the web UI can switch views.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.routing.channels.dispatch import DispatchResult, dispatch_decision
from app.core.routing.routing_data import get_store
from app.core.routing.schemas import RouteDecision

logger = logging.getLogger(__name__)

_routing_store = get_store()


class WebPresenter:
    """Present L0 routing decisions to the web channel as JSON response bodies."""

    source = "web"
    macro_timeout = None

    async def on_agent(self, _decision: Any) -> DispatchResult:
        return DispatchResult(handled=False, payload=None)

    async def on_local(
        self,
        _decision: Any,
        _action: str,
        _args: dict[str, Any],
        route: str | None,
    ) -> DispatchResult:
        if route is not None:
            return DispatchResult(
                handled=True,
                payload={
                    "status": "done",
                    "action_type": "navigate",
                    "navigate": route,
                    "summary": _routing_store.builtin_responses["generic"]["ok"],
                },
            )
        # Non-navigate local actions (e.g., open_app, mute) are not directly
        # executable by the web backend; delegate to the Agent.
        return DispatchResult(handled=False, payload=None)

    async def on_builtin(
        self,
        _decision: Any,
        _action: str,
        _args: dict[str, Any],
        outcome: Any,
    ) -> DispatchResult:
        return DispatchResult(
            handled=True,
            payload={
                "status": "done" if outcome.ok else "failed",
                "action_type": "builtin",
                "summary": outcome.message,
            },
        )

    async def on_macro(
        self,
        _decision: Any,
        _macro_id: int,
        _args: dict[str, Any],
        outcome: Any,
    ) -> DispatchResult:
        if outcome.action_type == "navigate":
            return DispatchResult(
                handled=True,
                payload={
                    "status": "done",
                    "action_type": "navigate",
                    "navigate": outcome.data.get("route"),
                    "summary": _routing_store.builtin_responses["generic"]["ok"],
                },
            )
        return DispatchResult(
            handled=True,
            payload={
                "status": "done" if outcome.ok else "failed",
                "action_type": "macro",
                "summary": outcome.message,
                "fell_back": outcome.data.get("fell_back", False),
            },
        )


async def execute_route_for_web(
    decision: RouteDecision,
    *,
    thread_id: str,
    project_id: int,
) -> dict[str, Any] | None:
    """Execute a routed decision for the web channel.

    Returns a response dict when the action can be handled locally (macro,
    builtin, navigate). Returns ``None`` when the decision should be delegated
    to the Agent.
    """
    presenter = WebPresenter()
    result = await dispatch_decision(
        decision,
        presenter,
        thread_id=thread_id,
        project_id=project_id,
    )
    return result.payload
