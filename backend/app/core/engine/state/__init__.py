"""Agent engine state models package."""

from typing import Any

from app.core.engine.state.base import AgentState, AgentStateBase, StateUpdate
from app.core.engine.state.blackboard import (
    BlackboardMetadata,
    BlackboardState,
    BlackboardVerification,
    PendingAggregation,
    SpawnPlan,
    SpawnPlanSubtask,
    SubtaskResult,
    merge_blackboard,
)
from app.core.engine.state.config import (
    AgentRuntimeConfig,
    ExecutionTicket,
    RunnableConfigMetadata,
    TicketParameters,
)
from app.core.engine.state.hitl import HITLContext, HITLState, MessagePayload
from app.core.engine.state.workspace import (
    ClipboardItem,
    ClipboardMetadata,
    RetrievalContext,
    SubtaskContext,
    WorkspaceContext,
)


def ensure_state(state: Any) -> AgentState:
    """Ensures that the state is an AgentState object (hydrating from dict if necessary)."""
    if isinstance(state, AgentState):
        return state
    if isinstance(state, dict):
        try:
            return AgentState.model_validate(state)
        except (TypeError, ValueError):
            # Fallback to keyword unpacking if validation fails (backward compatibility)
            return AgentState(**state)

    # If it's another object, but has dictionary interface or is a Pydantic model
    if hasattr(state, "model_dump"):
        return AgentState.model_validate(state.model_dump())
    elif hasattr(state, "__dict__") and not isinstance(state, (str, int, float, list, tuple)):
        return AgentState(**state.__dict__)

    return state
