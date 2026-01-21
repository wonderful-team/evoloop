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

    def capture_snapshot(self, path: str):
        """
        Reads the current content of the file and stores it in memory.
        Call this BEFORE executing an edit tool.
        """
        try:
            with open(path, encoding="utf-8") as f:
                self._snapshots[path] = f.read()
            # logger.debug(f"Captured snapshot for {path} ({len(self._snapshots[path])} chars)")
        except FileNotFoundError:
            # File might mean to be created
            self._snapshots[path] = ""
        except Exception as e:
            logger.warning(f"Failed to capture snapshot for {path}: {e}")

    def compute_diff(self, path: str) -> str:
        """
        Reads the file AGAIN and computes diff vs snapshot.
        Call this AFTER executing an edit tool.
        Returns empty string if no change or no snapshot.
        """
        if path not in self._snapshots:
            return ""

        old_content = self._snapshots.pop(path)  # Consume snapshot

        try:
            with open(path, encoding="utf-8") as f:
                new_content = f.read()
        except FileNotFoundError:
            # File deleted?
            new_content = ""

        if old_content == new_content:
            return ""

        # Compute Unified Diff
        diff = difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=2,  # Context lines
        )

        diff_text = "".join(diff)
        return diff_text

    def clear(self):
        self._snapshots.clear()


# Global singleton for the engine to use
diff_tracker = DiffTracker()
