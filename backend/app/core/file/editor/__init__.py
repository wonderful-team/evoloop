"""
Core file editing engine - Fuzzy matching and replacement strategies.

This module provides the foundational editing capabilities used by file tools.
"""

from .algorithms import calculate_confidence, generate_unified_diff, levenshtein
from .engine import EditEngine
from .models import (
    EditFileRequest,
    EditPreviewResult,
    FileEditOperation,
    MatchConfidence,
)
from .service import FileEditorService
from .strategies import (
    STRATEGIES,
    block_anchor_replacer,
    context_aware_replacer,
    escape_normalized_replacer,
    indentation_flexible_replacer,
    line_trimmed_replacer,
    multi_occurrence_replacer,
    simple_replacer,
    trimmed_boundary_replacer,
    whitespace_normalized_replacer,
)

__all__ = [
    # Services
    "FileEditorService",
    # Main engine
    "EditEngine",
    # Models
    "MatchConfidence",
    "EditPreviewResult",
    "FileEditOperation",
    "EditFileRequest",
    # Strategy list and individual strategies
    "STRATEGIES",
    "simple_replacer",
    "line_trimmed_replacer",
    "block_anchor_replacer",
    "whitespace_normalized_replacer",
    "trimmed_boundary_replacer",
    "escape_normalized_replacer",
    "context_aware_replacer",
    "indentation_flexible_replacer",
    "multi_occurrence_replacer",
    # Algorithms
    "levenshtein",
    "generate_unified_diff",
    "calculate_confidence",
]
