"""Top-level AgentState and StateUpdate models."""
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import Field, field_validator

from app.core.engine.state.blackboard import (
    BlackboardState,
    merge_blackboard,
)
from app.core.engine.state.workspace import WorkspaceContext
from app.infrastructure.pydantic_base import DynamicBaseModel


class AgentStateBase(DynamicBaseModel):
    """Shared base for AgentState and StateUpdate."""
    thread_id: str | None = None
    project_id: int | None = None
    current_plan: str | None = None
    structured_plan: str | None = None
    workspace_context: WorkspaceContext | None = None
    execution_artifact: str | None = None
    blackboard: BlackboardState | None = None
    error: str | None = None
    user_preferences: Any | None = None
    situation_analysis: str | None = None
    action_plan: str | None = None
    skill_execution_attempted: bool | None = None
    active_tool_profile: str | None = None
    tool_history: list[str] = Field(default_factory=list)

    # Runtime / transient fields
    is_subtask: bool | None = None
    relevant_sops: list[Any] = Field(default_factory=list)

    # Hydration deduplication marker
    hydration_marker: str | None = None


class AgentState(AgentStateBase):
    """Top-level Agent State for LangGraph."""
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    is_retry: bool | None = None
    iteration_count: int = 0
    next_node: Annotated[str | None, lambda a, b: b] = None
    blackboard: Annotated[BlackboardState, merge_blackboard] = Field(default_factory=BlackboardState)

    @field_validator("blackboard", mode="before")
    @classmethod
    def _ensure_blackboard(cls, v):
        """Backward-compat: ensure we have a BlackboardState instance."""
        if v is None:
            return BlackboardState()
        if isinstance(v, dict):
            return BlackboardState.model_validate(v)
        return v

    @field_validator("error", mode="before")
    @classmethod
    def _ensure_error_string(cls, v):
        """Backward-compat: some nodes or old checkpoints may store error as a dict."""
        if isinstance(v, dict):
            import json
            try:
                # If it's a structured error, try to extract a friendly message or type
                if "message" in v:
                    return v["message"]
                if "error_type" in v:
                    return f"Error ({v.get('category', 'UNKNOWN')}): {v['error_type']}"
                return json.dumps(v, ensure_ascii=False)
            except Exception:
                return str(v)
        return v


class StateUpdate(AgentStateBase):
    """Standardized state update returned by LangGraph nodes."""
    messages: list[BaseMessage] | None = None
    next_node: str | None = None
    iteration_count: int | None = None
