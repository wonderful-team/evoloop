"""
StateLifecycleManager - Declarative state lifecycle management.

Provides centralized helpers for nodes to consume and clear state fields
after use, preventing stale state from leaking across turns.
"""

import logging

from app.core.engine.schemas import WorkerOutcome
from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


class StateLifecycleManager:
    """
    Declarative lifecycle helpers for AgentState transitions.

    Nodes call consume_* helpers after reading a field to ensure it is cleared
    and cannot cause accidental routing loops on retry.
    """

    @staticmethod
    def consume_worker_outcome(state: AgentState) -> WorkerOutcome | None:
        """Consume and clear state.worker_outcome."""
        outcome = state.worker_outcome
        if outcome is not None:
            state.worker_outcome = None
            logger.debug(f"[Lifecycle] Consumed worker_outcome='{outcome}'")
        return outcome

    @staticmethod
    def consume_next_node(state: AgentState) -> str | None:
        """Consume and clear state.next_node."""
        target = state.next_node
        if target is not None:
            state.next_node = None
            logger.debug(f"[Lifecycle] Consumed next_node='{target}'")
        return target

    @staticmethod
    def consume_blocked_by_hook(state: AgentState) -> bool:
        """Consume and clear blocked_by_hook flag."""
        blocked = state.blocked_by_hook or False
        if state.blocked_by_hook is not None:
            state.blocked_by_hook = None
            logger.debug("[Lifecycle] Consumed blocked_by_hook")
        return blocked
