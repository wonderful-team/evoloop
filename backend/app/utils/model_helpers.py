from typing import Any, Optional


class LegacyDictMixin:
    """
    Mixin to provide dict-like access to Pydantic models for backward compatibility.
    
    Supports:
    - model["field"]
    - model.get("field", default)
    """

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)
