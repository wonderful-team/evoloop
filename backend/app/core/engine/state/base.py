"""Top-level AgentState and StateUpdate models."""
import operator
from typing import Annotated, Any, List, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import Field
from app.infrastructure.pydantic_base import DynamicBaseModel

from app.core.engine.state.blackboard import BlackboardState, VerificationStatus, merge_blackboard
from app.core.engine.state.config import ExecutionTicket
from app.core.engine.state.hitl import HITLState
from app.core.engine.state.workspace import RetrievalContext, WorkspaceContext


class AgentStateBase(DynamicBaseModel):
    """Shared base for AgentState and StateUpdate."""
    thread_id: Optional[str] = None
    project_id: Optional[int] = None
    current_plan: Optional[str] = None
    structured_plan: Optional[str] = None
    context: Optional[RetrievalContext] = None
    workspace_context: Optional[WorkspaceContext] = None
    execution_artifact: Optional[str] = None
    blackboard: Optional[BlackboardState] = None
    error: Optional[str] = None
    execution_ticket: Optional[ExecutionTicket] = None
    user_preferences: Optional[str] = None
    situation_analysis: Optional[str] = None
    action_plan: Optional[str] = None
    skill_execution_attempted: Optional[bool] = None
    active_tool_profile: Optional[str] = None
    hitl_state: Optional[HITLState] = None
    tool_history: List[str] = Field(default_factory=list)

    # Runtime / transient fields
    is_subtask: Optional[bool] = None
    relevant_sops: List[Any] = Field(default_factory=list)

    # Legacy: prefer blackboard.verification; kept for backward compatibility
    verification_status: Optional[VerificationStatus] = None


class AgentState(AgentStateBase):
    """Top-level Agent State for LangGraph."""
    messages: Annotated[List[BaseMessage], add_messages] = Field(default_factory=list)
    is_retry: Optional[bool] = None
    iteration_count: int = 0
    next_node: Annotated[Optional[str], lambda a, b: b] = None
    blackboard: Annotated[Optional[BlackboardState], merge_blackboard] = None


class StateUpdate(AgentStateBase):
    """Standardized state update returned by LangGraph nodes."""
    messages: Optional[List[BaseMessage]] = None
    next_node: Optional[str] = None
    iteration_count: Optional[int] = None
