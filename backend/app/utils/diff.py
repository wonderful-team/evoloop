"""
Text diff utilities for tracking file changes.

This module provides tools for capturing file snapshots and computing
differences between file versions using unified diff format.
"""

import difflib
import logging
import os
import threading

logger = logging.getLogger(__name__)

#: 二进制文件快照占位前缀（后接字节数），text diff 无法对二进制内容生成，
#: 但可据此保持 ADD/EDIT/DELETE 的存在性/变化跟踪，且不触发 UnicodeDecodeError。
BINARY_FILE_MARKER = "__EVOLOOP_BINARY__"


def is_binary_content(content: str) -> bool:
    """判断读出的内容是否为二进制占位（``read_text_or_binary`` 产物）。"""
    return content.startswith(BINARY_FILE_MARKER)


def read_text_or_binary(path: str) -> str:
    """读取文件：文本文件返回 UTF-8 内容；二进制文件返回二进制占位串。

    以字节方式读取后判 UTF-8 可解码性，避免对 PNG/图片等二进制文件抛出
    ``UnicodeDecodeError``（原实现对二进制快照会刷告警并丢失存在性跟踪）。
    占位串记录字节数，使 compute_diff 仍能判定 ADD/EDIT/DELETE。
    """
    with open(path, "rb") as f:
        raw = f.read()
    if b"\x00" in raw:
        return f"{BINARY_FILE_MARKER}:{len(raw)}"
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return f"{BINARY_FILE_MARKER}:{len(raw)}"


class DiffStats:
    """Statistics about the difference between two texts."""

    lines_added: int
    lines_removed: int
    lines_unchanged: int
    chars_changed: int

    def __init__(self, lines_added: int, lines_removed: int, lines_unchanged: int, chars_changed: int):
        self.lines_added = lines_added
        self.lines_removed = lines_removed
        self.lines_unchanged = lines_unchanged
        self.chars_changed = chars_changed

    def __getitem__(self, key: str):
        return getattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)


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
        self._lock = threading.Lock()

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
            content = read_text_or_binary(path)
        except FileNotFoundError:
            # File might mean to be created
            content = ""
        except (OSError, TypeError, ValueError) as e:
            logger.warning(f"Failed to capture snapshot for {path} (thread {thread_id}): {e}", exc_info=True)
            return

        with self._lock:
            self._snapshots[key] = content

    def compute_diff(
        self, path: str, thread_id: str = "default", context_lines: int = 2
    ) -> tuple[str, str, str | None]:
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
        with self._lock:
            old_content = self._snapshots.pop(key, None)  # Consume snapshot
        if old_content is None:
            return "", "", None

        try:
            new_content = read_text_or_binary(path)
        except FileNotFoundError:
            # File deleted?
            new_content = ""

        if old_content == new_content:
            return "", "", None

        # Binary files cannot be text-diffed; only report existence-level change.
        if is_binary_content(old_content) or is_binary_content(new_content):
            operation = "EDIT"
            if not old_content and new_content:
                operation = "ADD"
            elif old_content and not new_content:
                operation = "DELETE"
            # No text content to serve as an undo backup for binary files.
            return operation, "", None

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
        with self._lock:
            return key in self._snapshots

    def get_snapshot(self, path: str, thread_id: str = "default") -> str | None:
        """Read the stored snapshot WITHOUT consuming it.

        Returns ``None`` when no snapshot exists；空文件快照存的是 ``""``。
        """
        key = f"{thread_id}:{path}"
        with self._lock:
            return self._snapshots.get(key)

    def drop_snapshot(self, path: str, thread_id: str = "default") -> None:
        """Remove a snapshot without computing a diff."""
        key = f"{thread_id}:{path}"
        with self._lock:
            self._snapshots.pop(key, None)

    def clear(self, thread_id: str | None = None) -> None:
        """
        Clear snapshots.

        Args:
            thread_id: If provided, only clear snapshots for this thread.
                      If None, clear all snapshots.
        """
        with self._lock:
            if thread_id is None:
                self._snapshots.clear()
            else:
                prefix = f"{thread_id}:"
                for key in list(self._snapshots):
                    if key.startswith(prefix):
                        del self._snapshots[key]

    def get_snapshot_count(self, thread_id: str | None = None) -> int:
        """
        Get number of stored snapshots.

        Args:
            thread_id: If provided, count only snapshots for this thread.

        Returns:
            Number of snapshots
        """
        with self._lock:
            if thread_id is None:
                return len(self._snapshots)
            prefix = f"{thread_id}:"
            return sum(1 for k in self._snapshots if k.startswith(prefix))


def compute_text_diff(
    old_text: str,
    new_text: str,
    old_label: str = "original",
    new_label: str = "modified",
    context_lines: int = 3,
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


def get_diff_stats(old_text: str, new_text: str) -> DiffStats:
    """
    Get statistics about the difference between two texts.

    Args:
        old_text: Original text
        new_text: Modified text

    Returns:
        DiffStats with diff statistics:
        - lines_added: Number of lines added
        - lines_removed: Number of lines removed
        - lines_unchanged: Number of unchanged lines
        - chars_changed: Total characters changed
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    sm = difflib.SequenceMatcher(None, old_lines, new_lines)

    lines_added = 0
    lines_removed = 0
    lines_unchanged = 0
    chars_changed = 0

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            lines_unchanged += i2 - i1
        elif tag == "delete":
            lines_removed += i2 - i1
            chars_changed += sum(len(line) for line in old_lines[i1:i2])
        elif tag == "insert":
            lines_added += j2 - j1
            chars_changed += sum(len(line) for line in new_lines[j1:j2])
        elif tag == "replace":
            lines_removed += i2 - i1
            lines_added += j2 - j1
            chars_changed += (
                sum(len(line) for line in old_lines[i1:i2]) +
                sum(len(line) for line in new_lines[j1:j2])
            )

    return DiffStats(
        lines_added=lines_added,
        lines_removed=lines_removed,
        lines_unchanged=lines_unchanged,
        chars_changed=chars_changed,
    )


# Global singleton for convenience
diff_tracker = DiffTracker()
