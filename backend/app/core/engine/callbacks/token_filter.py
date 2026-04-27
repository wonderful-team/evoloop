"""
Token filter for LLM streaming — detects hidden tags, extracts thinking tokens,
and manages publish buffer.
"""

import logging

logger = logging.getLogger(__name__)

# Tags that should be completely hidden (not even thinking)
HIDDEN_TAGS_START = [
    "<evoloop_session_audit>", "<evoloop_audit_outcome>",
    "<evoloop_audit_reason>", "<evoloop_audit_proof>",
]
HIDDEN_TAGS_END = [
    "</evoloop_session_audit>", "</evoloop_audit_outcome>",
    "</evoloop_audit_reason>", "</evoloop_audit_proof>",
]

# Thinking tags — content inside these should be extracted for streaming display
THINKING_TAGS_START = [
    "<think>", "<thought>", "<|channel|>thought", "<|channel>thought",
]
THINKING_TAGS_END = [
    "</think>", "</thought>", "<|channel|>", "<channel|>",
]

STRIP_TAGS = ["<evoloop_final_report>", "</evoloop_final_report>"]


class TokenFilter:
    """Filters LLM tokens: hides internal tags, extracts thinking for streaming."""

    def __init__(self):
        self._in_hidden_tag = False
        self._in_thinking_tag = False
        self._tag_buffer = ""
        self._publish_buffer = ""
        self._thinking_buffer = ""

    def process(self, token: str) -> tuple[str | None, str | None]:
        """
        Process a single token.

        Returns:
            (publish_token, thinking_token):
            - publish_token: token to stream to frontend (None if suppressed)
            - thinking_token: token inside thinking tags to stream as thinking (None if not thinking)
        """
        was_hidden = self._in_hidden_tag
        was_thinking = self._in_thinking_tag

        self._tag_buffer += token
        if len(self._tag_buffer) > 100:
            self._tag_buffer = self._tag_buffer[-100:]

        # 1. Detect start of thinking tags
        if not self._in_hidden_tag and not self._in_thinking_tag:
            for tag in THINKING_TAGS_START:
                if tag in self._tag_buffer:
                    self._in_thinking_tag = True
                    self._tag_buffer = ""
                    # The start tag itself is not thinking content
                    return None, None

        # 2. Detect start of hidden tags (non-thinking)
        if not self._in_hidden_tag and not self._in_thinking_tag:
            for tag in HIDDEN_TAGS_START:
                if tag in self._tag_buffer:
                    self._in_hidden_tag = True
                    self._tag_buffer = ""
                    break

        # 3. Detect end of thinking tags
        if was_thinking and self._in_thinking_tag:
            for tag in THINKING_TAGS_END:
                idx = self._tag_buffer.find(tag)
                if idx != -1:
                    self._in_thinking_tag = False
                    # Preserve anything AFTER the end tag (e.g. <think> immediately following <channel|>)
                    after_end = self._tag_buffer[idx + len(tag):]
                    self._tag_buffer = after_end
                    # Flush any remaining thinking buffer
                    remaining = self._thinking_buffer
                    self._thinking_buffer = ""
                    # Check if a new thinking/hidden tag starts right after the end tag
                    if after_end:
                        for st in THINKING_TAGS_START:
                            if st in after_end:
                                self._in_thinking_tag = True
                                self._tag_buffer = ""
                                return None, remaining if remaining else None
                        for st in HIDDEN_TAGS_START:
                            if st in after_end:
                                self._in_hidden_tag = True
                                self._tag_buffer = ""
                                return None, remaining if remaining else None
                    return None, remaining if remaining else None
            # Still inside thinking tag — accumulate and return as thinking token
            self._thinking_buffer += token
            return None, token

        # 4. Detect end of hidden tags
        if was_hidden and self._in_hidden_tag:
            for tag in HIDDEN_TAGS_END:
                idx = self._tag_buffer.find(tag)
                if idx != -1:
                    self._in_hidden_tag = False
                    # Preserve anything AFTER the end tag for subsequent start-tag detection
                    self._tag_buffer = self._tag_buffer[idx + len(tag):]
                    break
            return None, None

        if self._in_hidden_tag:
            return None, None

        # 5. Normal token — strip marker tags and accumulate
        content = token
        for tag in STRIP_TAGS:
            content = content.replace(tag, "")

        self._publish_buffer += content
        return content, None

    def should_flush(self) -> bool:
        """Check if the publish buffer should be flushed."""
        return "\n" in self._publish_buffer or len(self._publish_buffer) > 50

    def flush(self) -> str:
        """Return and clear the publish buffer."""
        buf = self._publish_buffer
        self._publish_buffer = ""
        return buf

    def flush_thinking(self) -> str:
        """Return and clear the thinking buffer."""
        buf = self._thinking_buffer
        self._thinking_buffer = ""
        return buf

    def reset(self):
        """Reset all internal state."""
        self._in_hidden_tag = False
        self._in_thinking_tag = False
        self._tag_buffer = ""
        self._publish_buffer = ""
        self._thinking_buffer = ""
