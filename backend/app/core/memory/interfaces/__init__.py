"""Memory component interfaces."""

from app.core.memory.interfaces.base import IMemoryProvider
from app.core.memory.interfaces.graph import IGraphNavigator
from app.core.memory.interfaces.long_term import (
    Concept,
    Episode,
    ILongTermMemory,
    SearchResult,
)
from app.core.memory.interfaces.preferences import IPreferenceStore
from app.core.memory.interfaces.short_term import IShortTermMemory

__all__ = [
    "IMemoryProvider",
    "IShortTermMemory",
    "ILongTermMemory",
    "IPreferenceStore",
    "IGraphNavigator",
    "Concept",
    "Episode",
    "SearchResult",
]
