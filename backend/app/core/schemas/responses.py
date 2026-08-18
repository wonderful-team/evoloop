"""Standard API response envelopes — shared across core and api layers.

Envelope contract (see ``docs/api-response-envelope.md``):

- Success (single object) -> ``DataResponse[T]``
- Success (list / paginated) -> ``ListResponse[T]``
- Error -> ``ErrorResponse``, produced automatically by the global handlers in
  ``app/api/errors.py`` (never construct error JSON by hand).

Backward-compat: error ``detail`` keeps its original value so legacy clients
that read ``body.detail`` keep working.
"""

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


class ListResponse(BaseAPIResponse, Generic[T]):
    """Paginated list response."""

    data: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class ErrorResponse(BaseAPIResponse):
    """Standard error response."""

    success: bool = False
    code: str = "UNKNOWN_ERROR"
    detail: Any | None = None
