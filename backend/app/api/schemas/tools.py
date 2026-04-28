"""API schemas for tools routes."""

from app.infrastructure.pydantic_base import DynamicBaseModel
from typing import Any
from typing import Any, Optional

class ToolInfo(DynamicBaseModel):
    name: str
    description: str
    args_schema: dict[str, Any] | None = None
    is_runtime: bool | None = None
