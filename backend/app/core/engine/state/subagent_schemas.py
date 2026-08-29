"""Subagent schemas — plan, subtask, result and need_input data classes.

Design: docs/subagent-design.md §3.4.
"""

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class SubagentPlanSubtask(DynamicBaseModel):
    id: str  # e.g. "sub-0"
    instruction: str
    role: str = "Subagent"
    focus_paths: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    skill_hint: str | None = None
    tools: list[str] | None = None
    system_instructions: str | None = None


class SubagentPlan(DynamicBaseModel):
    subtasks: list[SubagentPlanSubtask] = Field(default_factory=list)
    requires_aggregation: bool = True
    aggregation_strategy: str = "merge"  # "merge" | "concatenate" | "summarize"
    parent_task: str = ""
    max_parallel: int = 5


class SubagentNeedInput(DynamicBaseModel):
    subagent_id: str | None = None
    question: str
    options: list[str] = Field(default_factory=list)
    context: str = ""
    source_task_id: str | None = None


class SubagentResult(DynamicBaseModel):
    subagent_id: str
    status: str  # "completed" | "failed" | "cancelled"
    result: str
    error: str | None = None
    tools_used: list[str] = Field(default_factory=list)
    need_input: SubagentNeedInput | None = None
    timestamp: float | None = None
