from pydantic import BaseModel, ConfigDict

from app.utils.model_helpers import LegacyDictMixin


class DynamicBaseModel(BaseModel, LegacyDictMixin):
    """
    Base model allowing extra fields and dict-like access.
    Use this for dynamic schemas, state bags, and loose payloads.
    """

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)
