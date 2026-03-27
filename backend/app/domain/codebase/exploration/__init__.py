"""
Unified Code Exploration Layer

Provides semantic tools for code exploration with automatic backend selection.
Agent says WHAT to find, system decides HOW to find it.

Note: search_code has been merged into search_files (domain/tools/files/)
"""

from .engine import CodeExplorationEngine
from .tools import (
    find_symbol,
    ask_codebase,
    analyze_impact,
    check_types,
    inspect_symbol,
)

__all__ = [
    "CodeExplorationEngine",
    "find_symbol",
    "ask_codebase",
    "analyze_impact",
    "check_types",
    "inspect_symbol",
]
