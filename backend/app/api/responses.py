from typing import Any, Generic, TypeVar

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel

T = TypeVar("T")


class BaseAPIResponse(DynamicBaseModel):
    """Standard API response envelope with success/message."""

    success: bool = True
    message: str = ""


class DataResponse(BaseAPIResponse):
    """Response carrying a single data payload."""

    data: Any | None = None


import warnings

with warnings.catch_warnings():
    # Silencing Pydantic's UserWarning about 'items' shadowing LegacyDictMixin.items()
    warnings.simplefilter("ignore", category=UserWarning)

    class ListResponse(BaseAPIResponse, Generic[T]):
        """Paginated list response."""

        items: list[T] = Field(default_factory=list)
        total: int = 0
        page: int = 1
        page_size: int = 20


class ErrorResponse(BaseAPIResponse):
    """Standard error response."""

    success: bool = False
    code: str = "UNKNOWN_ERROR"
    detail: Any | None = None
