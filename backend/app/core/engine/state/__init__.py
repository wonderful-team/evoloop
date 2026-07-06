"""Agent engine state models package."""

from typing import Any

from app.core.engine.state.base import AgentState, StateUpdate
from app.core.engine.state.config import (
    AgentRuntimeConfig,
    ExecutionTicket,
    RunnableConfigMetadata,
)

__all__ = [
    "AgentState",
    "StateUpdate",
    "AgentRuntimeConfig",
    "ExecutionTicket",
    "RunnableConfigMetadata",
    "ensure_state",
]


def ensure_state(state: Any) -> AgentState:
    """Ensures that the state is an AgentState object (hydrating from dict if necessary)."""
    if isinstance(state, AgentState):
        return state

    if isinstance(state, dict):
        return AgentState.model_validate(state)

    # If it's a Pydantic model or similar
    if hasattr(state, "model_dump"):
        return AgentState.model_validate(state.model_dump())

    return state
