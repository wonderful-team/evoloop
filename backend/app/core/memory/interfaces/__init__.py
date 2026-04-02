"""Memory component interfaces."""

from app.core.memory.interfaces.base import IMemoryProvider
from app.core.memory.interfaces.short_term import IShortTermMemory

__all__ = [
    "IMemoryProvider",
    "IShortTermMemory",
]
