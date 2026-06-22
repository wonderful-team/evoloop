"""
StateLifecycleManager - Declarative state lifecycle management.

Provides centralized helpers for nodes to consume and clear state fields
after use, preventing stale state from leaking across turns.
"""

import logging

from app.core.engine.state import AgentState

logger = logging.getLogger(__name__)


class StateLifecycleManager:
    """
    Declarative lifecycle helpers for AgentState transitions.

    Nodes call consume_* helpers after reading a field to ensure it is cleared
    and cannot cause accidental routing loops on retry.
    """

    @staticmethod
    def consume_worker_outcome(state: AgentState) -> str | None:
        """Consume and clear state.worker_outcome."""
        outcome = state.worker_outcome
        if outcome is not None:
            state.worker_outcome = None
            logger.debug(f"[Lifecycle] Consumed worker_outcome='{outcome}'")
        return outcome

    @staticmethod
    def consume_spawn_plan(state: AgentState) -> None:
        """Consume and clear state.spawn_plan."""
        if state.spawn_plan is not None:
            state.spawn_plan = None
            logger.debug("[Lifecycle] Consumed spawn_plan")

    @staticmethod
    def consume_next_node(state: AgentState) -> str | None:
        """Consume and clear state.next_node."""
        target = state.next_node
        if target is not None:
            state.next_node = None
            logger.debug(f"[Lifecycle] Consumed next_node='{target}'")
        return target

    @staticmethod
    def clear_aggregation_state(state: AgentState) -> None:
        """Clear all orchestration-related fields after aggregation."""
        cleared = []
        for field in ("pending_aggregation", "subtask_results", "spawn_plan"):
            if getattr(state, field) is not None:
                if field == "subtask_results":
                    setattr(state, field, [])
                else:
                    setattr(state, field, None)
                cleared.append(field)
        if cleared:
            logger.debug(f"[Lifecycle] Cleared aggregation state: {cleared}")

    @staticmethod
    def clear_workflow_state(state: AgentState) -> None:
        """Clear sequential workflow state from state."""
        cleared = []
        for field in ("workflow_plan", "workflow_step_index", "workflow_results"):
            if getattr(state, field) is not None:
                setattr(state, field, None)
                cleared.append(field)
        if cleared:
            logger.debug(f"[Lifecycle] Cleared workflow state: {cleared}")

    @staticmethod
    def reset_terminal_metadata(state: AgentState) -> None:
        """Reset terminal metadata fields that should not persist across runs."""
        for field in ("final_outcome", "shadow_audit", "blocked_by_hook"):
            if getattr(state, field) is not None:
                setattr(state, field, None)
                logger.debug(f"[Lifecycle] Reset metadata.{field}")

    @staticmethod
    def consume_blocked_by_hook(state: AgentState) -> bool:
        """Consume and clear blocked_by_hook flag."""
        blocked = state.blocked_by_hook or False
        if state.blocked_by_hook is not None:
            state.blocked_by_hook = None
            logger.debug("[Lifecycle] Consumed blocked_by_hook")
        return blocked
