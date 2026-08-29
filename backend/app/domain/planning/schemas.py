"""Schemas for planning module."""

from typing import Literal

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.id import gen_uuid


class Step(DynamicBaseModel):
    id: str = Field(default_factory=gen_uuid)
    title: str = Field(..., description="The description of the step")
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    sub_steps: list["Step"] = Field(default_factory=list)
    result: str | None = Field(None, description="The result or output of this step")


PlanStep = Step  # Alias for backward compatibility; TODO migrate usages to Step


class Plan(DynamicBaseModel):
    id: str = Field(default_factory=gen_uuid)
    title: str = Field(..., description="High level goal of this plan")
    steps: list[Step] = Field(default_factory=list)
    current_step_id: str | None = None
    is_complete: bool = False
