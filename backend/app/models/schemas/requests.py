"""Shared request/query schema bases."""

from app.infrastructure.pydantic_base import DynamicBaseModel


class BaseFilter(DynamicBaseModel):
    """Base class for filter/query parameters."""

    pass
