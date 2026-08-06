"""Channel-agnostic Layer-0 routing package.

Re-exports the most commonly used public symbols so callers can write
``from app.core.routing import CommandRouter`` instead of the full module path.
The underlying modules remain the source of truth; this file only re-exports.
"""

from app.core.routing.command_router import CommandRouter
from app.core.routing.conversation_state import ConversationState
from app.core.routing.decision_builder import build_decision
from app.core.routing.schemas import (
    IntentHint,
    RouteCatalog,
    RouteDecision,
)

__all__ = [
    # Schemas
    "IntentHint",
    "RouteCatalog",
    "RouteDecision",
    # Router
    "CommandRouter",
    "build_decision",
    # Multi-turn state
    "ConversationState",
]
