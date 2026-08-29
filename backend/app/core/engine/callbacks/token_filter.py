"""
Token filter for LLM streaming — detects hidden tags and manages publish buffer.

Removed: <think> / <thought> / <|channel|>thought tag handling.
Reasoning content now flows exclusively via native reasoning_content
(kimi-k2-thinking-turbo through Gateway), never embedded in content tags.
"""

import logging

from app.core.engine.constants import HIDDEN_TAGS_END, HIDDEN_TAGS_START, STRIP_TAGS

logger = logging.getLogger(__name__)


class TokenFilter:
    """Filters LLM tokens: hides internal tags, buffers publish content."""

    def __init__(self):
        self._in_hidden_tag = False
        self._tag_buffer = ""
        self._publish_buffer = ""

    def process(self, token: str) -> tuple[str | None, str | None]:
        """
        Process a single token.

        Returns:
            (publish_token, None):
            - publish_token: token to stream to frontend (None if inside hidden tag)
        """
        was_hidden = self._in_hidden_tag

        self._tag_buffer += token
        if len(self._tag_buffer) > 100:
            self._tag_buffer = self._tag_buffer[-100:]

        # 1. Detect start of hidden tags
        if not self._in_hidden_tag:
            for tag in HIDDEN_TAGS_START:
                if tag in self._tag_buffer:
                    self._in_hidden_tag = True
                    self._tag_buffer = ""
                    break

        # 2. Detect end of hidden tags
        if was_hidden and self._in_hidden_tag:
            for tag in HIDDEN_TAGS_END:
                idx = self._tag_buffer.find(tag)
                if idx != -1:
                    self._in_hidden_tag = False
                    # Preserve anything AFTER the end tag for subsequent start-tag detection
                    self._tag_buffer = self._tag_buffer[idx + len(tag) :]
                    break
            return None, None

        if self._in_hidden_tag:
            return None, None

        # 3. Normal token — strip marker tags and accumulate
        content = token
        for tag in STRIP_TAGS:
            content = content.replace(tag, "")

        self._publish_buffer += content
        return content, None

    def should_flush(self, char_limit: int = 150) -> bool:
        """Check if the publish buffer should be flushed (char limit)."""
        from app.utils.text import should_flush_text

        return should_flush_text(
            self._publish_buffer,
            min_chars=char_limit,
        )

    def flush(self) -> str:
        """Return and clear the publish buffer."""
        buf = self._publish_buffer
        self._publish_buffer = ""
        return buf

    def reset(self):
        """Reset all internal state."""
        self._in_hidden_tag = False
        self._tag_buffer = ""
        self._publish_buffer = ""
