"""Blackboard state models and merge reducer."""
import logging
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from app.core.engine.state.config import ExecutionTicket
from app.core.engine.state.workspace import ClipboardItem, SubtaskContext
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
    context: SubtaskContext | None = None
    dependencies: list[str] | None = None
    tools: list[str] | None = None
    skill_hint: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_subtask_id(cls, data: Any) -> Any:
        if isinstance(data, dict) and "subtask_id" in data and "id" not in data:
            data = dict(data)
            data["id"] = data.pop("subtask_id")
        return data


class SpawnPlan(DynamicBaseModel):
    subtasks: list[SpawnPlanSubtask] = Field(default_factory=list)
    requires_aggregation: bool = True
    parent_task: str = ""
    aggregation_strategy: str = "merge"
    routing_signal: str | None = None
    suggested_skill: str | None = None


class PendingAggregation(DynamicBaseModel):
    strategy: str
    expected_count: int
    actual_count: int | None = None
    parent_task: str = ""


class SubtaskResult(DynamicBaseModel):
    subtask_id: str
    status: str
    result: Any
    tools_used: list[str] | None = None
    timestamp: float | None = None


class AuditMeta(DynamicBaseModel):
    tier: str
    duration_ms: float | None = None
    tools: list[str] | None = None


class BlackboardMetadata(DynamicBaseModel):
    tool_memory: dict | None = None
    final_outcome: str | None = None
    shadow_audit: bool | None = None
    termination_outcome: str | None = None
    last_aggregation_result: str | None = None
    audit_tier: str | None = None
    audit_meta: AuditMeta | None = None
    blocked_by_hook: bool | None = None
    tool_history: list[str] = Field(default_factory=list)


class WorkflowStepResult(DynamicBaseModel):
    skill_id: int | str | None = None
    skill_name: str | None = None
    output: str | None = None
    status: str | None = None


class MergePolicy(str, Enum):
    """Field-level merge policy for blackboard reducers."""

    REPLACE = "replace"
    APPEND = "append"
    APPEND_UNIQUE = "append_unique"
    MERGE_DICT = "merge_dict"
    DEDUP_APPEND = "dedup_append"


class BlackboardState(DynamicBaseModel):
    ticket: ExecutionTicket | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    verification: BlackboardVerification | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    route_reason: str | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    metadata: BlackboardMetadata = Field(
        default_factory=BlackboardMetadata,
        json_schema_extra={"merge_policy": MergePolicy.MERGE_DICT},
    )
    clipboard: list[ClipboardItem] = Field(
        default_factory=list,
        json_schema_extra={"merge_policy": MergePolicy.APPEND},
    )
    visited_nodes: list[str] = Field(
        default_factory=list,
        json_schema_extra={"merge_policy": MergePolicy.APPEND_UNIQUE},
    )
    working_directory: str | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    spawn_plan: SpawnPlan | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    pending_aggregation: PendingAggregation | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    subtask_results: list[SubtaskResult] = Field(
        default_factory=list,
        json_schema_extra={
            "merge_policy": MergePolicy.DEDUP_APPEND,
            "dedup_key": "subtask_id",
        },
    )
    plan_approved: bool | None = Field(
        default=False, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    worker_outcome: str | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    workflow_results: list[WorkflowStepResult] | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    workflow_plan: list[Any] | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    workflow_step_index: int | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    summary: str | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    active_subagents: list[dict[str, Any]] | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    completed_subagents: list[dict[str, Any]] | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    remaining_work: str | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    current_goal: str | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    test_failures: Any | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )
    lint_errors: Any | None = Field(
        default=None, json_schema_extra={"merge_policy": MergePolicy.REPLACE}
    )


def _resolve_field_policy(field_name: str, field_info: Any) -> tuple[MergePolicy, str | None]:
    """Read merge_policy (and optional dedup_key) from Field json_schema_extra."""
    extra = field_info.json_schema_extra
    policy = MergePolicy.REPLACE
    dedup_key = None
    if isinstance(extra, dict):
        policy = extra.get("merge_policy", MergePolicy.REPLACE)
        dedup_key = extra.get("dedup_key")
    return policy, dedup_key


def merge_blackboard(old: Any, new: Any) -> BlackboardState | None:
    """Merge two blackboard values. Accepts instances or dicts (from LangGraph serde)."""
    if old is None:
        return BlackboardState.model_validate(new) if new is not None else None
    if new is None:
        return BlackboardState.model_validate(old)

    old = BlackboardState.model_validate(old)
    new = BlackboardState.model_validate(new)

    merged = old.model_copy(deep=True)

    for field_name, field_info in BlackboardState.model_fields.items():
        policy, dedup_key = _resolve_field_policy(field_name, field_info)
        new_val = getattr(new, field_name, None)

        if new_val is None and field_name not in new.model_fields_set:
            # OPTIMIZATION: Do not overwrite with None if the field was not explicitly set.
            # This allows nodes to return StateUpdate objects with missing fields (defaulting to None)
            # without wiping the global blackboard state.
            continue

        if policy == MergePolicy.REPLACE:
            setattr(merged, field_name, new_val)
        elif policy == MergePolicy.APPEND:
            old_list = list(getattr(merged, field_name, None) or [])
            setattr(merged, field_name, old_list + list(new_val))
        elif policy == MergePolicy.APPEND_UNIQUE:
            old_list = list(getattr(merged, field_name, None) or [])
            existing = set(old_list)
            merged_list = old_list + [item for item in new_val if item not in existing]
            setattr(merged, field_name, merged_list)
        elif policy == MergePolicy.MERGE_DICT:
            old_meta = getattr(merged, field_name, None)
            old_dict = old_meta.model_dump() if old_meta is not None else {}
            new_dict = new_val.model_dump() if new_val is not None else {}
            # Only overwrite with non-None new values to avoid wiping existing state
            merged_dict = {**old_dict, **{k: v for k, v in new_dict.items() if v is not None}}
            field_type = type(old_meta) if old_meta is not None else type(new_val)
            setattr(merged, field_name, field_type.model_validate(merged_dict))
        elif policy == MergePolicy.DEDUP_APPEND:
            if not new_val:
                setattr(merged, field_name, new_val)
            else:
                old_list = list(getattr(merged, field_name, None) or [])
                seen = {
                    getattr(r, dedup_key)
                    for r in old_list
                    if dedup_key and getattr(r, dedup_key, None) is not None
                }
                delta = []
                for r in new_val:
                    key = getattr(r, dedup_key, None) if dedup_key else None
                    if not key or key not in seen:
                        delta.append(r)
                    else:
                        logger.debug(
                            f"[State] ℹ️ Subtask ID collision/sync for '{key}' - skipping duplicate."
                        )
                setattr(merged, field_name, old_list + delta)
        else:
            # Fallback for unknown policies
            setattr(merged, field_name, new_val)

    # DynamicBaseModel allows extra fields; preserve any extras coming from `new`
    new_extras = getattr(new, "model_extra", None) or {}
    for key, val in new_extras.items():
        setattr(merged, key, val)

    return merged
