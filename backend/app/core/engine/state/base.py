"""Top-level AgentState and StateUpdate models: SDK-free, no external framework dependencies."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from app.core.engine.message.native_classes import BaseMessage
from app.core.engine.state.config import ExecutionTicket
from app.core.engine.state.sub_schemas import (
    AuditAnomaly,
    AuditInputData,
    AuditMeta,
    PendingApproval,
    PlanProgress,
    VerificationStatus,
    WorkflowStepResult,
)
from app.core.engine.state.workspace import ClipboardItem, WorkspaceContext
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.models.learning import LearnedSkill


class AgentStateBase(DynamicBaseModel):
    # --- 1. Conversation ---
    messages: list[BaseMessage] = Field(default_factory=list)
    tool_history: list[str] = Field(default_factory=list)

    # --- 2. Execution ---
    thread_id: str | None = None
    project_id: int | None = None
    working_directory: str | None = None
    session_goal: str | None = None
    current_goal: str | None = None
    ticket: ExecutionTicket | None = None
    verification: VerificationStatus | None = None
    route_reason: str | None = None
    worker_outcome: str | None = None
    summary: str | None = None
    remaining_work: str | None = None
    blocked_by_hook: bool | None = None

    # --- 3. Planning ---
    current_plan: str | None = None
    structured_plan: str | None = None
    plan_approved: bool | None = False
    plan_progress: PlanProgress | None = None
    skill_execution_attempted: bool | None = None
    active_tool_profile: str | None = None
    relevant_sops: list[LearnedSkill] = Field(default_factory=list)

    # --- 4. Orchestration ---
    workflow_results: list[WorkflowStepResult] | None = None
    workflow_plan: list[LearnedSkill] | None = None
    workflow_step_index: int | None = None
    pending_signals: list[dict[str, Any]] = Field(default_factory=list)
    pending_approvals: list[PendingApproval] = Field(default_factory=list)
    shared_context: dict[str, str] = Field(default_factory=dict)
    max_supervisor_steps: int | None = None
    signal_queue_total: int = 0
    tool_memory: dict | None = None

    # --- 5. Audit ---
    audit_tier: str | None = None
    audit_meta: AuditMeta | None = None
    audit_input_data: AuditInputData | None = None
    audit_anomalies: list[AuditAnomaly] = Field(default_factory=list)
    final_outcome: str | None = None
    shadow_audit: bool | None = None
    termination_outcome: str | None = None
    force_comprehensive_audit: bool | None = None
    test_failures: Any | None = None
    lint_errors: Any | None = None

    # --- 6. Telemetry & Workspace ---
    tool_memory: dict | None = None
    visited_nodes: list[str] = Field(default_factory=list)
    workspace_context: WorkspaceContext | None = None
    execution_artifact: str | None = None
    error: str | None = None
    user_preferences: Any | None = None
    situation_analysis: str | None = None
    action_plan: str | None = None
    clipboard: list[ClipboardItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _pre_validate_state(cls, data: Any) -> Any:
        if isinstance(data, dict):
            messages = data.get("messages")
            if isinstance(messages, list):
                for msg in messages:
                    if not isinstance(msg, BaseMessage):
                        raise TypeError(
                            f"state.messages must contain BaseMessage instances, got {type(msg).__name__}. "
                            "Use HumanMessage/AIMessage/SystemMessage/ToolMessage objects."
                        )
        return data

    @property
    def metadata(self) -> dict[str, Any]:
        return self.build_metadata_dict()

    def build_metadata_dict(self) -> dict[str, Any]:
        fields = {
            "tool_history": self.tool_history,
            "pending_approvals": [x.model_dump() if hasattr(x, "model_dump") else x for x in (self.pending_approvals or [])],
            "audit_anomalies": [x.model_dump() if hasattr(x, "model_dump") else x for x in (self.audit_anomalies or [])],
            "tool_memory": self.tool_memory,
            "final_outcome": self.final_outcome,
            "shadow_audit": self.shadow_audit,
            "termination_outcome": self.termination_outcome,
            "audit_tier": self.audit_tier,
            "audit_meta": self.audit_meta.model_dump() if hasattr(self.audit_meta, "model_dump") and self.audit_meta else self.audit_meta,
            "blocked_by_hook": self.blocked_by_hook,
            "plan_progress": self.plan_progress.model_dump() if hasattr(self.plan_progress, "model_dump") and self.plan_progress else self.plan_progress,
            "max_supervisor_steps": self.max_supervisor_steps,
            "audit_input_data": self.audit_input_data.model_dump() if hasattr(self.audit_input_data, "model_dump") and self.audit_input_data else self.audit_input_data,
            "force_comprehensive_audit": self.force_comprehensive_audit,
        }
        return {k: v for k, v in fields.items() if v is not None}

    @property
    def blackboard(self) -> Any:
        return self


def merge_dicts(a: dict | None, b: dict | None) -> dict:
    """Merge two optional dicts; values from ``b`` override ``a``."""
    result = dict(a or {})
    if b:
        result.update(b)
    return result


def add_unique_items(a: list | None, b: list | None) -> list:
    """Concatenate two optional lists while preserving order and removing duplicates."""
    combined = (a or []) + (b or [])
    seen: set = set()
    result = []
    for item in combined:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


class AgentState(AgentStateBase):
    workspace_context: WorkspaceContext | None = None
    tool_history: list[str] = Field(default_factory=list)
    relevant_sops: list[LearnedSkill] = Field(default_factory=list)
    thread_id: str | None = None
    project_id: int | None = None
    is_retry: bool | None = None
    iteration_count: int = 0
    next_node: str | None = None
    session_goal: str | None = None


class StateUpdate(AgentStateBase):
    next_node: str | None = None
    iteration_count: int | None = None
    resume_tool_call: dict[str, Any] | None = None
