"""Top-level AgentState and StateUpdate models."""
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import Field

from app.core.engine.state.blackboard import (
    BlackboardState,
    VerificationStatus,
    merge_blackboard,
)
from app.core.engine.state.config import ExecutionTicket
from app.core.engine.state.hitl import HITLState
from app.core.engine.state.workspace import RetrievalContext, WorkspaceContext
from app.infrastructure.pydantic_base import DynamicBaseModel


class AgentStateBase(DynamicBaseModel):
    """Shared base for AgentState and StateUpdate."""
    thread_id: str | None = None
    project_id: int | None = None
    current_plan: str | None = None
    structured_plan: str | None = None
    context: RetrievalContext | None = None
    workspace_context: WorkspaceContext | None = None
    execution_artifact: str | None = None
    blackboard: BlackboardState | None = None
    error: str | None = None
    execution_ticket: ExecutionTicket | None = None
    user_preferences: str | None = None
    situation_analysis: str | None = None
    action_plan: str | None = None
    skill_execution_attempted: bool | None = None
    active_tool_profile: str | None = None
    hitl_state: HITLState | None = None
    tool_history: list[str] = Field(default_factory=list)

    # Runtime / transient fields
    is_subtask: bool | None = None
    relevant_sops: list[Any] = Field(default_factory=list)

    # Legacy: prefer blackboard.verification; kept for backward compatibility
    verification_status: VerificationStatus | None = None


class AgentState(AgentStateBase):
    """Top-level Agent State for LangGraph."""
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    is_retry: bool | None = None
    iteration_count: int = 0
    next_node: Annotated[str | None, lambda a, b: b] = None
    blackboard: Annotated[BlackboardState | None, merge_blackboard] = None


class StateUpdate(AgentStateBase):
    """Standardized state update returned by LangGraph nodes."""
    messages: list[BaseMessage] | None = None
    next_node: str | None = None
    iteration_count: int | None = None
