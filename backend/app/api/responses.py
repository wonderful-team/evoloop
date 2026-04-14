from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class BaseAPIResponse(DynamicBaseModel):
    """Standard API response envelope with success/message."""

    success: bool = True
    message: str = ""


class DataResponse(BaseAPIResponse):
    """Response carrying a single data payload."""

    data: Any | None = None


class ListResponse(BaseAPIResponse):
    """Paginated list response."""

    items: list[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class ErrorResponse(BaseAPIResponse):
    """Standard error response."""

    success: bool = False
    code: str = "UNKNOWN_ERROR"
    detail: Any | None = None
