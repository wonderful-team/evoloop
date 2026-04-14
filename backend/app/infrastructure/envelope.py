from typing import Any

from app.infrastructure.pydantic_base import DynamicBaseModel


class TaskEnvelope(DynamicBaseModel):
    """
    Generic envelope for cross-module task dispatching.
    Used when a module wants to hand off work without importing
    the receiver's domain models (Anti-Corruption Layer).
    """

    task_type: str
    payload: dict[str, Any] = {}
    metadata: dict[str, Any] = {}


class ResultEnvelope(DynamicBaseModel):
    """
    Generic envelope for task results returned across module boundaries.
    """

    success: bool = True
    payload: dict[str, Any] | None = None
    error: str | None = None
