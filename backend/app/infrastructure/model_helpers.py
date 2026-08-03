from collections.abc import Iterator
from typing import Any


class LegacyDictMixin:
    """
    Mixin to provide dict-like access to Pydantic models for backward compatibility.

    Supports:
    - model["field"]
    - model.get("field", default)
    - model["field"] = value
    - model.update({...})
    - dict(model)
    - "field" in model
    """

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        try:
            delattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key: str, default: Any | None = None) -> Any:
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def keys(self) -> set[str]:
        """Return a set of all field names (defined + extra)."""
        keys_set = set(self.model_fields.keys())
        model_extra = getattr(self, "model_extra", None)
        if model_extra:
            keys_set.update(model_extra.keys())
        return keys_set

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def items(self) -> Iterator[tuple[str, Any]]:
        for key in self.keys():
            yield key, getattr(self, key)

    def values(self) -> Iterator[Any]:
        for key in self.keys():
            yield getattr(self, key)

    def update(self, other: dict[str, Any]) -> None:
        for key, value in other.items():
            setattr(self, key, value)

    def pop(self, key: str, *args: Any) -> Any:
        if len(args) > 1:
            raise TypeError(f"pop expected at most 2 arguments, got {1 + len(args)}")
        try:
            value = getattr(self, key)
            delattr(self, key)
            return value
        except AttributeError:
            if args:
                return args[0]
            raise KeyError(key)

    def setdefault(self, key: str, default: Any | None = None) -> Any:
        if key in self:
            return getattr(self, key)
        setattr(self, key, default)
        return default
