"""Build ``RouteDecision`` objects from resolved L0 actions."""

from __future__ import annotations

from typing import Any

from app.core.routing.constants import INTENT_MACRO_TASK
from app.core.routing.schemas import IntentHint, RouteDecision


def build_decision(
    action: str,
    args: dict[str, Any],
    confidence: float,
    source: str,
    *,
    previous_intent: str | None = None,
    session_history: list[str] | None = None,
) -> RouteDecision:
    """Turn an L0 action tuple into a channel-independent routing decision."""
    if action.startswith("macro:"):
        macro_id = int(action.split(":", 1)[1])
        return RouteDecision(
            status="routed",
            target_type="macro",
            target={"type": "macro", "id": macro_id},
            params=args,
            confidence=confidence,
            intent_hint=IntentHint(
                intent=INTENT_MACRO_TASK,
                confidence=confidence,
                suggested_modules=["Base", "Macro"],
                reason="L0 macro match",
                previous_intent=previous_intent,
                session_history=session_history,
            ),
            source=source,
        )

    return RouteDecision(
        status="routed",
        target_type="local",
        target={"type": "local", "action": action},
        params=args,
        confidence=confidence,
        intent_hint=IntentHint(
            intent=INTENT_MACRO_TASK,
            confidence=confidence,
            suggested_modules=["Base"],
            reason="L0 local action match",
            previous_intent=previous_intent,
            session_history=session_history,
        ),
        source=source,
    )


__all__ = ["build_decision"]
