"""Top-level AgentState and StateUpdate models."""
import operator
from typing import Annotated, Any, Callable

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import Field, field_validator, model_validator

from app.core.engine.state.blackboard import (
    SubtaskResult,
    PendingApproval,
    AuditAnomaly,
    VerificationStatus,
    SpawnPlan,
    PendingAggregation,
    WorkflowStepResult,
    AuditMeta,
    PlanProgress,
    TaskDeliverable,
    ProgressMetrics,
    AuditInputData,
)
from app.core.engine.state.workspace import WorkspaceContext, ClipboardItem
from app.core.engine.state.config import ExecutionTicket
from app.infrastructure.pydantic_base import DynamicBaseModel


# --- Native Reducer Helpers ---

def merge_dicts(old: dict | None, new: dict | None) -> dict:
    """Combines dictionaries (non-recursive flat map)."""
    res = dict(old or {})
    res.update(new or {})
    return res


def add_unique_items(old: list | None, new: list | None) -> list:
    """Appends elements to a list, filtering out duplicates."""
    old_list = list(old or [])
    seen = set(old_list)
    return old_list + [item for item in (new or []) if item not in seen]


def add_unique_subtasks(old: list[SubtaskResult] | None, new: list[SubtaskResult] | None) -> list[SubtaskResult]:
    """Appends subtask results, deduplicating by subtask_id."""
    old_list = list(old or [])
    seen_ids = {r.subtask_id for r in old_list if hasattr(r, "subtask_id")}
    
    delta = []
    for r in (new or []):
        if isinstance(r, dict):
            r = SubtaskResult.model_validate(r)
        
        sid = r.subtask_id
        if sid not in seen_ids:
            delta.append(r)
            seen_ids.add(sid)
    return old_list + delta


class AgentStateBase(DynamicBaseModel):
    """Shared base for AgentState and StateUpdate."""
    thread_id: str | None = None
    project_id: int | None = None
    current_plan: str | None = None
    structured_plan: str | None = None
    workspace_context: WorkspaceContext | None = None
    execution_artifact: str | None = None
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

    # Session-level immutable goal (user's original request)
    session_goal: str | None = None

    # --- Elevated Sequential State Fields ---
    ticket: ExecutionTicket | None = None
    verification: VerificationStatus | None = None
    route_reason: str | None = None
    working_directory: str | None = None
    spawn_plan: SpawnPlan | None = None
    pending_aggregation: PendingAggregation | None = None
    plan_approved: bool | None = False
    worker_outcome: str | None = None
    workflow_results: list[WorkflowStepResult] | None = None
    workflow_plan: list[Any] | None = None
    workflow_step_index: int | None = None
    summary: str | None = None
    active_subagents: list[dict[str, Any]] | None = None
    completed_subagents: list[dict[str, Any]] | None = None
    remaining_work: str | None = None
    current_goal: str | None = None
    test_failures: Any | None = None
    lint_errors: Any | None = None
    signal_queue_total: int = 0
    tool_memory: dict | None = None
    final_outcome: str | None = None
    shadow_audit: bool | None = None
    termination_outcome: str | None = None
    last_aggregation_result: str | None = None
    audit_tier: str | None = None
    audit_meta: AuditMeta | None = None
    blocked_by_hook: bool | None = None
    plan_progress: PlanProgress | None = None
    max_supervisor_steps: int | None = None
    audit_input_data: AuditInputData | None = None
    force_comprehensive_audit: bool | None = None

    @property
    def metadata(self) -> dict[str, Any]:
        """Backward-compatibility: return a dictionary of elevated metadata fields."""
        metadata_fields = {
            "tool_history": self.tool_history,
            "pending_approvals": [x.model_dump() if hasattr(x, "model_dump") else x for x in (self.pending_approvals or [])],
            "audit_anomalies": [x.model_dump() if hasattr(x, "model_dump") else x for x in (self.audit_anomalies or [])],
            "tool_memory": self.tool_memory,
            "final_outcome": self.final_outcome,
            "shadow_audit": self.shadow_audit,
            "termination_outcome": self.termination_outcome,
            "last_aggregation_result": self.last_aggregation_result,
            "audit_tier": self.audit_tier,
            "audit_meta": self.audit_meta.model_dump() if hasattr(self.audit_meta, "model_dump") and self.audit_meta else self.audit_meta,
            "blocked_by_hook": self.blocked_by_hook,
            "plan_progress": self.plan_progress.model_dump() if hasattr(self.plan_progress, "model_dump") and self.plan_progress else self.plan_progress,
            "max_supervisor_steps": self.max_supervisor_steps,
            "audit_input_data": self.audit_input_data.model_dump() if hasattr(self.audit_input_data, "model_dump") and self.audit_input_data else self.audit_input_data,
            "force_comprehensive_audit": self.force_comprehensive_audit,
        }
        return {k: v for k, v in metadata_fields.items() if v is not None}

    @property
    def blackboard(self) -> Any:
        """Backward-compatibility: allow accessing elevated fields via .blackboard."""
        return self



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

    # --- Elevated Parallel State Fields with Reducers ---
    subtask_results: Annotated[list[SubtaskResult], add_unique_subtasks] = Field(default_factory=list)
    clipboard: Annotated[list[ClipboardItem], operator.add] = Field(default_factory=list)
    visited_nodes: Annotated[list[str], add_unique_items] = Field(default_factory=list)
    pending_signals: Annotated[list[dict[str, Any]], operator.add] = Field(default_factory=list)
    shared_context: Annotated[dict[str, str], merge_dicts] = Field(default_factory=dict)
    pending_approvals: Annotated[list[PendingApproval], operator.add] = Field(default_factory=list)
    audit_anomalies: Annotated[list[AuditAnomaly], operator.add] = Field(default_factory=list)

    @field_validator("error", mode="before")
    @classmethod
    def _ensure_error_string(cls, v):
        """Backward-compat: some nodes or old checkpoints may store error as a dict."""
        if isinstance(v, dict):
            import json
            try:
                if "message" in v:
                    return v["message"]
                if "error_type" in v:
                    return f"Error ({v.get('category', 'UNKNOWN')}): {v['error_type']}"
                return json.dumps(v, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(v)
        return v

    @model_validator(mode="after")
    def _validate_reducers(self):
        """Ensure every field that may be updated by parallel branches has an Annotated reducer."""
        allowed_plain = {
            "thread_id", "project_id", "current_plan", "structured_plan",
            "execution_artifact", "error", "user_preferences", "situation_analysis",
            "action_plan", "skill_execution_attempted", "active_tool_profile",
            "is_subtask", "session_goal", "ticket", "verification", "route_reason",
            "working_directory", "spawn_plan", "pending_aggregation", "plan_approved",
            "worker_outcome", "workflow_results", "workflow_plan", "workflow_step_index",
            "summary", "active_subagents", "completed_subagents", "remaining_work",
            "current_goal", "test_failures", "lint_errors", "signal_queue_total",
            "tool_memory", "final_outcome", "shadow_audit", "termination_outcome",
            "last_aggregation_result", "audit_tier", "audit_meta", "blocked_by_hook",
            "plan_progress", "max_supervisor_steps", "audit_input_data", "force_comprehensive_audit"
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
    resume_tool_call: dict[str, Any] | None = None
    subtask_results: list[SubtaskResult] | None = None
    clipboard: list[ClipboardItem] | None = None
    visited_nodes: list[str] | None = None
    pending_signals: list[dict[str, Any]] | None = None
    shared_context: dict[str, str] | None = None
    pending_approvals: list[PendingApproval] | None = None
    audit_anomalies: list[AuditAnomaly] | None = None
