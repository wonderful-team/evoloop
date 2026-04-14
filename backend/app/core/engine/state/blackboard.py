"""Blackboard state models and merge reducer."""
import logging
from typing import Any

from pydantic import Field

from app.core.engine.state.config import ExecutionTicket
from app.core.engine.state.workspace import ClipboardItem
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class VerificationStatus(DynamicBaseModel):
    status: str
    signals: list[str] = Field(default_factory=list)


# Backward-compatible alias
BlackboardVerification = VerificationStatus


class SpawnPlanSubtask(DynamicBaseModel):
    id: str
    intent: str
    description: str | None = None
    title: str | None = None
    context: Any | None = None
    dependencies: list[str] | None = None
    tools: list[str] | None = None
    skill_hint: str | None = None


class SpawnPlan(DynamicBaseModel):
    subtasks: list[SpawnPlanSubtask] = Field(default_factory=list)
    _requires_aggregation: bool = True
    parent_task: str = ""
    aggregation_strategy: str = "merge"
    _routing_signal: str | None = None


class PendingAggregation(DynamicBaseModel):
    strategy: str
    expected_count: int
    actual_count: int | None = None


class SubtaskResult(DynamicBaseModel):
    subtask_id: str
    status: str
    result: Any
    tools_used: list[str] | None = None
    timestamp: float | None = None


class BlackboardMetadata(DynamicBaseModel):
    pass


class BlackboardState(DynamicBaseModel):
    ticket: ExecutionTicket | None = None
    verification: BlackboardVerification | None = None
    route_reason: str | None = None
    metadata: BlackboardMetadata = Field(default_factory=BlackboardMetadata)
    clipboard: list[ClipboardItem] = Field(default_factory=list)
    visited_nodes: list[str] = Field(default_factory=list)
    working_directory: str | None = None
    spawn_plan: SpawnPlan | None = None
    pending_aggregation: PendingAggregation | None = None
    subtask_results: list[SubtaskResult] = Field(default_factory=list)
    plan_approved: bool = False
    worker_outcome: str | None = None


def merge_blackboard(old: BlackboardState | None, new: BlackboardState | dict[str, Any] | None) -> BlackboardState | None:
    if old is None:
        if isinstance(new, dict):
            return BlackboardState.model_validate(new)
        return new
    if new is None:
        return old
    if isinstance(new, dict):
        new = BlackboardState.model_validate(new)

    merged = old.model_copy(deep=True)

    simple_fields = [
        "ticket", "verification", "route_reason", "spawn_plan",
        "pending_aggregation", "working_directory", "plan_approved", "worker_outcome"
    ]
    for key in simple_fields:
        val = getattr(new, key, None)
        if val is not None:
            setattr(merged, key, val)

    if new.subtask_results is not None:
        if not new.subtask_results:
            merged.subtask_results = []
        else:
            old_results = list(merged.subtask_results or [])
            seen_ids = {r.subtask_id for r in old_results if r.subtask_id}
            delta = []
            for r in new.subtask_results:
                sid = r.subtask_id
                if not sid or sid not in seen_ids:
                    delta.append(r)
                else:
                    logger.debug(f"[State] ℹ️ Subtask ID collision/sync for '{sid}' - skipping duplicate.")
            merged.subtask_results = old_results + delta

    if new.metadata is not None:
        old_meta = dict(merged.metadata) if merged.metadata else {}
        merged.metadata = {**old_meta, **dict(new.metadata)}

    if new.visited_nodes is not None:
        old_nodes = list(merged.visited_nodes or [])
        combined = old_nodes + [n for n in new.visited_nodes if n not in old_nodes]
        merged.visited_nodes = combined

    if new.clipboard is not None:
        merged.clipboard = list(merged.clipboard or []) + list(new.clipboard)

    return merged
