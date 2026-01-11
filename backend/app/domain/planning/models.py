from typing import List, Optional, Literal
from app.utils.id import gen_uuid

from pydantic import BaseModel, Field


class Step(BaseModel):
    id: str = Field(default_factory=gen_uuid)
    title: str = Field(..., description="The description of the step")
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    sub_steps: List["Step"] = Field(default_factory=list)
    result: Optional[str] = Field(None, description="The result or output of this step")


class Plan(BaseModel):
    id: str = Field(default_factory=gen_uuid)
    title: str = Field(..., description="High level goal of this plan")
    steps: List[Step] = Field(default_factory=list)
    current_step_id: Optional[str] = None
    is_complete: bool = False
