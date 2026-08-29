"""
Shared Tree-sitter Queries for Code Analysis and Extraction.

.. deprecated::
    The ``TREE_SITTER_QUERIES`` dictionary now lives in
    ``app.domain.codebase.constants``. This module re-exports it for
    backward compatibility; new code should import from the constants module.
"""

from app.domain.codebase.constants import TREE_SITTER_QUERIES

__all__ = ["TREE_SITTER_QUERIES"]
