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
        if "messages" in state and state["messages"]:
            from app.core.engine.message.converter import EvoMessageConverter

            state = {**state, "messages": EvoMessageConverter.repair(state["messages"])}
        return AgentState.model_validate(state)

    if hasattr(state, "model_dump"):
        data = state.model_dump()
        if "messages" in data and data["messages"]:
            from app.core.engine.message.converter import EvoMessageConverter

            data["messages"] = EvoMessageConverter.repair(data["messages"])
        return AgentState.model_validate(data)

    return state
