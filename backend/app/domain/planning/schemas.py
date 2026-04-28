"""Schemas for planning module."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils.id import gen_uuid


class Step(DynamicBaseModel):
    id: str = Field(default_factory=gen_uuid)
    title: str = Field(..., description="The description of the step")
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    sub_steps: list["Step"] = Field(default_factory=list)
    result: str | None = Field(None, description="The result or output of this step")


PlanStep = Step  # Alias for backward compatibility; TODO migrate usages to Step


class PlanDefinition(BaseModel):
    title: str
    steps: list[PlanStep] = Field(default_factory=list)


class Plan(DynamicBaseModel):
    id: str = Field(default_factory=gen_uuid)
    title: str = Field(..., description="High level goal of this plan")
    steps: list[Step] = Field(default_factory=list)
    current_step_id: str | None = None
    is_complete: bool = False


class CreatePlanInput(BaseModel):
    title: str = Field(..., description="High level goal of the plan")
    steps: list[str] = Field(..., description="List of step titles")


class UpdatePlanInput(BaseModel):
    plan_id: str = Field(..., description="ID of the plan to update")
    step_id: str = Field(..., description="ID of the step to update")
    status: str = Field(..., description="New status: pending, in_progress, completed, failed")
    result: str | None = Field(None, description="Result of the step")
