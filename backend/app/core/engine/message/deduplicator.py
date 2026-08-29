"""
MessageDeduplicator — Simple time-windowed content deduplication.

Extracted from MessageHandler to separate deduplication concerns.
"""

import logging
import time

from app.core.engine.message.category import MessageCategory
from app.core.file import compute_md5

logger = logging.getLogger(__name__)


class MessageDeduplicator:
    """
    Simple deduplicator based on content hash and time window.

    NOTE: This is instance-local deduplication. For distributed deduplication
    across multiple workers, consider using a shared cache (FileCache/Redis).
    """

    def __init__(self, window_seconds: float = 2.0):
        self._window_seconds = window_seconds
        self._last_hash: str | None = None
        self._last_time: float = 0.0

    def is_duplicate(
        self, category: MessageCategory, content: str, tool_calls: list | None
    ) -> bool:
        """
        Check if the message is a duplicate of the recently processed one.

        Returns:
            True if duplicate (same hash within time window)
        """
        content_hash = compute_md5(f"{category.value}:{content}:{str(tool_calls)}")[:16]

        current_time = time.time()
        if (
            content_hash == self._last_hash
            and (current_time - self._last_time) < self._window_seconds
        ):
            return True

        self._last_hash = content_hash
        self._last_time = current_time
        return False

    def reset(self) -> None:
        """Reset deduplication state."""
        self._last_hash = None
        self._last_time = 0.0
