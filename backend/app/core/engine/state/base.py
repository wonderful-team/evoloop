"""Top-level AgentState and StateUpdate models."""
import operator
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import Field, field_validator, model_validator

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

    # Session-level immutable goal (user's original request)
    session_goal: str | None = None


class AgentState(AgentStateBase):
    """Top-level Agent State for LangGraph."""
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    workspace_context: Annotated[WorkspaceContext | None, lambda a, b: b] = None
    tool_history: Annotated[list[str], operator.concat] = Field(default_factory=list)
    relevant_sops: Annotated[list[Any], operator.concat] = Field(default_factory=list)
    thread_id: Annotated[str | None, lambda a, b: b if b is not None else a] = None
    project_id: Annotated[int | None, lambda a, b: b if b is not None else a] = None
    is_retry: Annotated[bool | None, lambda a, b: b if b is not None else a] = None
    iteration_count: Annotated[int, lambda a, b: b] = 0
    next_node: Annotated[str | None, lambda a, b: b] = None
    session_goal: Annotated[str | None, lambda a, b: b if b is not None else a] = None
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

    @model_validator(mode="after")
    def _validate_reducers(self):
        """Ensure every field that may be updated by parallel branches has an Annotated reducer."""
        allowed_plain = {
            "thread_id", "project_id", "current_plan", "structured_plan",
            "execution_artifact", "error", "user_preferences", "situation_analysis",
            "action_plan", "skill_execution_attempted", "active_tool_profile",
            "hydration_marker", "is_subtask", "session_goal",
        }
        missing = []
        for field_name, field_info in self.model_fields.items():
            if field_name in allowed_plain:
                continue
            if not field_info.metadata:
                missing.append(field_name)

        if missing:
            raise ValueError(
                f"AgentState fields must be Annotated with a LangGraph reducer to avoid InvalidUpdateError. "
                f"Missing reducers on: {missing}. "
                f"Wrap the type like `Annotated[T, reducer]`."
            )

        return self


class StateUpdate(AgentStateBase):
    """Standardized state update returned by LangGraph nodes."""
    messages: list[BaseMessage] | None = None
    next_node: str | None = None
    iteration_count: int | None = None
