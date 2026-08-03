"""State sub-schemas for agent state tracking."""

import logging
from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class VerificationStatus(DynamicBaseModel):
    status: str
    signals: list[str] = Field(default_factory=list)


class AuditMeta(DynamicBaseModel):
    tier: str
    duration_ms: float | None = None
    tools: list[str] | None = None


class PlanProgress(DynamicBaseModel):
    """Tracks completion progress of a structured plan."""

    total_steps: int = 0
    completed_steps: int = 0
    plan_id: str | None = None

    def is_complete(self) -> bool:
        return self.completed_steps >= self.total_steps


class TaskDeliverable(DynamicBaseModel):
    """Structured record of a single deliverable produced during task execution."""

    deliverable_type: str = ""  # e.g. "wiki_page", "file_edit", "test_case"
    title: str = ""
    slug: str | None = None
    summary: str = ""  # Brief summary for audit consumption
    word_count: int = 0
    created_at: str = ""  # ISO timestamp
    metadata: dict = Field(default_factory=dict)


class ProgressMetrics(DynamicBaseModel):
    """Progress metrics readable by Audit / Supervisor without parsing messages."""

    total_steps: int = 0
    completed_steps: int = 0
    total_deliverables: int = 0
    completed_deliverables: int = 0
    elapsed_time_seconds: float = 0.0
    estimated_remaining_seconds: float | None = None
    key_findings: list[str] = Field(default_factory=list)
    issues_encountered: list[str] = Field(default_factory=list)


class AuditAnomaly(DynamicBaseModel):
    """Anomaly flag raised by intermediate layers for audit attention."""

    anomaly_type: str = ""  # e.g. "context_overload", "single_turn_saturation"
    severity: str = "info"  # "info" | "warn" | "critical"
    description: str = ""
    suggested_action: str | None = None


class AuditInputData(DynamicBaseModel):
    """Structured audit input — replaces full message history for comprehensive audit."""

    original_goal: str = ""
    plan_summary: dict = Field(default_factory=dict)   # {total: N, completed: N, remaining: N}
    progress: ProgressMetrics = Field(default_factory=ProgressMetrics)
    deliverables: list[TaskDeliverable] = Field(default_factory=list)
    tool_stats: dict[str, int] = Field(default_factory=dict)
    anomalies: list[AuditAnomaly] = Field(default_factory=list)
    key_messages_digest: str = ""  # Optional: recent 10 messages digest


class PendingApproval(DynamicBaseModel):
    """A HITL authorization request that is waiting for user response."""

    tool_name: str = ""
    tool_call_id: str = ""
    resource_path: str = ""
    action: str = ""
    risk_level: str = "medium"
    requested_at: str = ""  # ISO timestamp
    tool_args: dict[str, Any] = Field(default_factory=dict)


class WorkflowStepResult(DynamicBaseModel):
    skill_id: int | str | None = None
    skill_name: str | None = None
    output: str | None = None
    status: str | None = None
