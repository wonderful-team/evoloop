"""
File change tracking for memory system.

This module re-exports DiffTracker from utils.diff for backward compatibility.
The actual implementation has been moved to app.utils.diff.
"""

# Re-export from utils for backward compatibility
from app.utils.diff import DiffTracker, diff_tracker, compute_text_diff, get_diff_stats

__all__ = ["DiffTracker", "diff_tracker", "compute_text_diff", "get_diff_stats"]
