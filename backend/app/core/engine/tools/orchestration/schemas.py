"""
Shared Pydantic schemas for orchestration tools.
"""

from app.core.engine.state.blackboard import SpawnPlan
from app.infrastructure.pydantic_base import DynamicBaseModel


class OrchestrationToolResult(DynamicBaseModel):
    status: str
    message: str
    _signal: str | None = None
    data: dict | None = None


class DecomposeTaskResult(DynamicBaseModel):
    status: str
    error: str | None = None
    routing_target: str | None = None
    spawn_plan: SpawnPlan | None = None
