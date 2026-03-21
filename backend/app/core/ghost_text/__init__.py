"""Ghost Text inline suggestions for code editing."""

from .suggester import (
    GhostTextSuggester,
    GhostSuggestion,
    EditPreview,
    ghost_suggester,
    suggest_ghost_text,
)

__all__ = [
    "GhostTextSuggester",
    "GhostSuggestion",
    "EditPreview",
    "ghost_suggester",
    "suggest_ghost_text",
]
