"""Subagent schemas — plan, subtask, result and need_input data classes.

Design: docs/subagent-design.md §3.4.
"""

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class SubagentNeedInput(DynamicBaseModel):
    subagent_id: str | None = None
    question: str
    options: list[str] = Field(default_factory=list)
    context: str = ""
    source_task_id: str | None = None
