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
    shared_context: dict[str, Any] = Field(default_factory=dict)
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
    # --- Audit rejection redo (Phase E3) ---
    audit_correctable: bool | None = None
    audit_reason: str | None = None
    audit_retry_count: int = 0

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
            "pending_approvals": [
                x.model_dump()
                for x in (self.pending_approvals or [])
            ],
            "audit_anomalies": [
                x.model_dump()
                for x in (self.audit_anomalies or [])
            ],
            "tool_memory": self.tool_memory,
            "final_outcome": self.final_outcome,
            "shadow_audit": self.shadow_audit,
            "termination_outcome": self.termination_outcome,
            "audit_tier": self.audit_tier,
            "audit_meta": self.audit_meta.model_dump() if self.audit_meta else None,
            "blocked_by_hook": self.blocked_by_hook,
            "plan_progress": self.plan_progress.model_dump() if self.plan_progress else None,
            "max_supervisor_steps": self.max_supervisor_steps,
            "audit_input_data": self.audit_input_data.model_dump() if self.audit_input_data else None,
            "force_comprehensive_audit": self.force_comprehensive_audit,
        }
        return {k: v for k, v in fields.items() if v is not None}

    @property
    def blackboard(self) -> Any:
        return self


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
    session_handoff: bool = False  # 会话模式：Supervisor 决策出 WORKER，交给主循环启动 rollout

    # --- Subagent (parallel execution) ---
    subagent_plan: dict | None = None  # SubagentPlan.model_dump()
    active_subagents: list[dict] = Field(default_factory=list)
    completed_subagents: list[dict] = Field(default_factory=list)
    pending_subagent_aggregation: dict | None = None
    pending_need_inputs: list[dict] = Field(default_factory=list)
    pending_subagent_hitl_requests: list[dict] = Field(default_factory=list)
    active_subagent_hitl: dict = Field(default_factory=dict)  # {sub_tid: tool_call_id}
    last_aggregation_result: str | None = None
    # 聚合轮标记：由 subagent_completed 唤醒（无用户新消息）时置位，
    # Supervisor 据此在"还有 subagent 在跑"时跳过 LLM 直接等待，避免陈旧上下文抢跑。
    subagent_aggregation_turn: bool = False
    # 聚合后呈现标记：AggregateSubagents 置位，Supervisor 据此禁止重新委派
    # （LLM 在聚合轮仍可能再次 route_to/spawn，需确定性收尾呈现聚合结果）。
    presentation_pending: bool = False


class StateUpdate(AgentStateBase):
    next_node: str | None = None
    iteration_count: int | None = None
    resume_tool_call: dict[str, Any] | None = None

    # --- Subagent (parallel execution): 显式声明，保证 merge_state_update 可写回
    # 且属性访问可用（不依赖 pydantic extra 隐式行为）。与 AgentState 对齐。
    subagent_plan: dict | None = None
    active_subagents: list[dict] = Field(default_factory=list)
    completed_subagents: list[dict] = Field(default_factory=list)
    pending_subagent_aggregation: dict | None = None
    pending_need_inputs: list[dict] = Field(default_factory=list)
    pending_subagent_hitl_requests: list[dict] = Field(default_factory=list)
    active_subagent_hitl: dict = Field(default_factory=dict)
    last_aggregation_result: str | None = None
    subagent_aggregation_turn: bool = False
    presentation_pending: bool = False
