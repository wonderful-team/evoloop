from typing import Literal

from pydantic import BaseModel, Field

from app.utils.id import gen_uuid
from app.utils.model_helpers import LegacyDictMixin


class Step(BaseModel, LegacyDictMixin):
    id: str = Field(default_factory=gen_uuid)
    title: str = Field(..., description="The description of the step")
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    sub_steps: list["Step"] = Field(default_factory=list)
    result: str | None = Field(None, description="The result or output of this step")


class Plan(BaseModel, LegacyDictMixin):
    id: str = Field(default_factory=gen_uuid)
    title: str = Field(..., description="High level goal of this plan")
    steps: list[Step] = Field(default_factory=list)
    current_step_id: str | None = None
    is_complete: bool = False
