"""API schemas for tools routes."""

from typing import Any

from app.infrastructure.pydantic_base import DynamicBaseModel


class ToolInfo(DynamicBaseModel):
    name: str
    description: str
    args_schema: dict[str, Any] | None = None
    is_runtime: bool | None = None
