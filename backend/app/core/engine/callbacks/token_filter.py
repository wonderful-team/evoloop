"""
Token filter for LLM streaming — detects hidden tags and manages publish buffer.
"""

import logging

logger = logging.getLogger(__name__)

HIDDEN_TAGS_START = [
    "<evoloop_session_audit>", "<think>", "<thought>",
    "<evoloop_audit_outcome>", "<evoloop_audit_reason>", "<evoloop_audit_proof>"
]
HIDDEN_TAGS_END = [
    "</evoloop_session_audit>", "</think>", "</thought>",
    "</evoloop_audit_outcome>", "</evoloop_audit_reason>", "</evoloop_audit_proof>"
]
STRIP_TAGS = ["<evoloop_final_report>", "</evoloop_final_report>"]


class TokenFilter:
    """Filters LLM tokens to hide internal tags from frontend streaming."""

    def __init__(self):
        self._in_hidden_tag = False
        self._tag_buffer = ""
        self._publish_buffer = ""

    def process(self, token: str) -> str | None:
        """
        Process a single token. Returns the filtered content to publish,
        or None if the token should be suppressed (inside a hidden tag).
        """
        self._tag_buffer += token
        if len(self._tag_buffer) > 100:
            self._tag_buffer = self._tag_buffer[-100:]

        # 1. Detect start of hidden tags
        if not self._in_hidden_tag:
            for tag in HIDDEN_TAGS_START:
                if tag in self._tag_buffer:
                    self._in_hidden_tag = True
                    break

        # 2. Detect end of hidden tags
        if self._in_hidden_tag:
            for tag in HIDDEN_TAGS_END:
                if tag in self._tag_buffer:
                    self._in_hidden_tag = False
                    self._tag_buffer = ""
                    break
            return None

        # 3. Strip marker tags
        content = token
        for tag in STRIP_TAGS:
            content = content.replace(tag, "")

        self._publish_buffer += content
        return content

    def should_flush(self) -> bool:
        """Check if the publish buffer should be flushed."""
        return "\n" in self._publish_buffer or len(self._publish_buffer) > 50

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
