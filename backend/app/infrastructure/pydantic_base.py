import time

from pydantic import BaseModel, ConfigDict, Field

from app.infrastructure.model_helpers import LegacyDictMixin


class DynamicBaseModel(BaseModel, LegacyDictMixin):
    """
    Base model allowing extra fields and dict-like access.
    Use this for dynamic schemas, state bags, and loose payloads.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class EventBase(DynamicBaseModel):
    """Base class for all SSE/streaming events with automatic timestamp."""
    timestamp: float = Field(default_factory=time.time)
