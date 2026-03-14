import difflib
import logging

logger = logging.getLogger(__name__)


class DiffTracker:
    """
    Tracks file changes to generate precise memory of what actually changed.
    Logic:
    1. capture_snapshot(path): Read file before edit.
    2. compute_diff(path): Read file after edit, compare with snapshot.
    """

    def __init__(self):
        self._snapshots: dict[str, str] = {}

    def capture_snapshot(self, path: str, thread_id: str = "default"):
        """
        Reads the current content of the file and stores it in memory.
        Call this BEFORE executing an edit tool.
        """
        key = f"{thread_id}:{path}"
        try:
            with open(path, encoding="utf-8") as f:
                self._snapshots[key] = f.read()
            # logger.debug(f"Captured snapshot for {path} ({len(self._snapshots[path])} chars)")
        except FileNotFoundError:
            # File might mean to be created
            self._snapshots[key] = ""
        except Exception as e:
            logger.warning(f"Failed to capture snapshot for {path} (thread {thread_id}): {e}")

    def compute_diff(self, path: str, thread_id: str = "default") -> tuple[str, str, str | None]:
        """
        Reads the file AGAIN and computes diff vs snapshot.
        Call this AFTER executing an edit tool.
        Returns (operation, diff, original_content).
        Returns ("", "", None) if no change or no snapshot.
        """
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
            n=2,  # Context lines
        )

        diff_text = "".join(diff)
        # Return original_content for Undo support
        # - ADD: old_content is empty (will be None for semantics)
        # - EDIT/DELETE: old_content is the backup
        original = old_content if old_content else None
        return operation, diff_text, original

    def clear(self):
        self._snapshots.clear()


# Global singleton for the engine to use
diff_tracker = DiffTracker()
