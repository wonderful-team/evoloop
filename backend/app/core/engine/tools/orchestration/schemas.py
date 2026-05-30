"""
Shared Pydantic schemas for orchestration tools.
"""

from app.core.engine.state.blackboard import SpawnPlan
from app.infrastructure.pydantic_base import DynamicBaseModel


class DecomposeTaskResult(DynamicBaseModel):
    status: str
    error: str | None = None
    spawn_plan: SpawnPlan | None = None
