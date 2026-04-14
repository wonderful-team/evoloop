"""Agent engine state models package."""

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

from typing import Any


def ensure_state(state: Any) -> AgentState:
    """Ensures that the state is an AgentState object (hydrating from dict if necessary)."""
    if isinstance(state, AgentState):
        return state
    if isinstance(state, dict):
        return AgentState(**state)
    return state
