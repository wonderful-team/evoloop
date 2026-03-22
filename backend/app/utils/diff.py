"""
Text diff utilities for tracking file changes.

This module provides tools for capturing file snapshots and computing
differences between file versions using unified diff format.
"""

import difflib
import logging
import os
from typing import Tuple

logger = logging.getLogger(__name__)


class DiffTracker:
    """
    Tracks file changes to generate precise memory of what actually changed.
    
    Logic:
    1. capture_snapshot(path): Read file before edit.
    2. compute_diff(path): Read file after edit, compare with snapshot.
    
    Example:
        tracker = DiffTracker()
        
        # Before edit
        tracker.capture_snapshot("/path/to/file.py", thread_id="task_1")
        
        # ... perform edit ...
        
        # After edit
        operation, diff, original = tracker.compute_diff("/path/to/file.py", thread_id="task_1")
        # operation: "ADD" | "EDIT" | "DELETE"
        # diff: unified diff text
        # original: original content (None if ADD)
    """

    def __init__(self):
        self._snapshots: dict[str, str] = {}

    def capture_snapshot(self, path: str, thread_id: str = "default") -> None:
        """
        Reads the current content of the file and stores it in memory.
        Call this BEFORE executing an edit tool.
        
        Args:
            path: File path to capture
            thread_id: Optional thread identifier for isolation
        """
        if os.path.isdir(path):
            return

        key = f"{thread_id}:{path}"
        try:
            with open(path, encoding="utf-8") as f:
                self._snapshots[key] = f.read()
        except FileNotFoundError:
            # File might mean to be created
            self._snapshots[key] = ""
        except Exception as e:
            logger.warning(f"Failed to capture snapshot for {path} (thread {thread_id}): {e}")

    def compute_diff(
        self, 
        path: str, 
        thread_id: str = "default",
        context_lines: int = 2
    ) -> Tuple[str, str, str | None]:
        """
        Reads the file AGAIN and computes diff vs snapshot.
        Call this AFTER executing an edit tool.
        
        Args:
            path: File path to compare
            thread_id: Optional thread identifier for isolation
            context_lines: Number of context lines in unified diff
        
        Returns:
            Tuple of (operation, diff, original_content)
            - operation: "ADD" | "EDIT" | "DELETE" | "" (no change)
            - diff: unified diff text (empty if no change)
            - original_content: original content or None (None if ADD or no change)
        """
        if os.path.isdir(path):
            return "", "", None

        key = f"{thread_id}:{path}"
        if key not in self._snapshots:
            return "", "", None

        old_content = self._snapshots.pop(key)  # Consume snapshot

        try:
            with open(path, encoding="utf-8") as f:
                new_content = f.read()
        except FileNotFoundError:
            # File deleted?
            new_content = ""

        if old_content == new_content:
            return "", "", None

        # Determine Operation
        operation = "EDIT"
        if not old_content and new_content:
            operation = "ADD"
        elif old_content and not new_content:
            operation = "DELETE"

        # Compute Unified Diff
        diff = difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=context_lines,
        )

        diff_text = "".join(diff)
        # Return original_content for Undo support
        # - ADD: old_content is empty (will be None for semantics)
        # - EDIT/DELETE: old_content is the backup
        original = old_content if old_content else None
        return operation, diff_text, original

    def has_snapshot(self, path: str, thread_id: str = "default") -> bool:
        """Check if a snapshot exists for the given path and thread."""
        key = f"{thread_id}:{path}"
        return key in self._snapshots

    def clear(self, thread_id: str | None = None) -> None:
        """
        Clear snapshots.
        
        Args:
            thread_id: If provided, only clear snapshots for this thread.
                      If None, clear all snapshots.
        """
        if thread_id is None:
            self._snapshots.clear()
        else:
            prefix = f"{thread_id}:"
            keys_to_remove = [k for k in self._snapshots if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._snapshots[key]

    def get_snapshot_count(self, thread_id: str | None = None) -> int:
        """
        Get number of stored snapshots.
        
        Args:
            thread_id: If provided, count only snapshots for this thread.
        
        Returns:
            Number of snapshots
        """
        if thread_id is None:
            return len(self._snapshots)
        prefix = f"{thread_id}:"
        return sum(1 for k in self._snapshots if k.startswith(prefix))


def compute_text_diff(
    old_text: str, 
    new_text: str,
    old_label: str = "original",
    new_label: str = "modified",
    context_lines: int = 3
) -> str:
    """
    Compute unified diff between two text strings.
    
    Args:
        old_text: Original text
        new_text: Modified text
        old_label: Label for original text in diff header
        new_label: Label for modified text in diff header
        context_lines: Number of context lines
    
    Returns:
        Unified diff text
    
    Example:
        >>> diff = compute_text_diff("hello\\nworld", "hello\\npython")
        >>> print(diff)
        --- original
        +++ modified
        @@ -1,2 +1,2 @@
         hello
        -world
        +python
    """
    diff = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=old_label,
        tofile=new_label,
        n=context_lines,
    )
    return "".join(diff)


def get_diff_stats(old_text: str, new_text: str) -> dict:
    """
    Get statistics about the difference between two texts.
    
    Args:
        old_text: Original text
        new_text: Modified text
    
    Returns:
        Dictionary with diff statistics:
        - lines_added: Number of lines added
        - lines_removed: Number of lines removed
        - lines_unchanged: Number of unchanged lines
        - chars_changed: Total characters changed
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    
    sm = difflib.SequenceMatcher(None, old_lines, new_lines)
    
    stats = {
        "lines_added": 0,
        "lines_removed": 0,
        "lines_unchanged": 0,
        "chars_changed": 0,
    }
    
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            stats["lines_unchanged"] += i2 - i1
        elif tag == "delete":
            stats["lines_removed"] += i2 - i1
            stats["chars_changed"] += sum(len(line) for line in old_lines[i1:i2])
        elif tag == "insert":
            stats["lines_added"] += j2 - j1
            stats["chars_changed"] += sum(len(line) for line in new_lines[j1:j2])
        elif tag == "replace":
            stats["lines_removed"] += i2 - i1
            stats["lines_added"] += j2 - j1
            stats["chars_changed"] += (
                sum(len(line) for line in old_lines[i1:i2]) +
                sum(len(line) for line in new_lines[j1:j2])
            )
    
    return stats


# Global singleton for convenience
diff_tracker = DiffTracker()
