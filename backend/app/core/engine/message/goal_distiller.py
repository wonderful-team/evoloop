"""
GoalDistiller — Goal normalization utility.

Provides a single, testable entry point for sanitizing a clean ``session_goal``
string.

Design rules:
- Pure / stateless: no DB calls, no LLM calls, no side effects.
- Returns a sanitized, truncated string that is safe for storage and display.
"""

import logging

logger = logging.getLogger(__name__)

# Maximum character length for a stored/displayed session goal.
# Longer text is truncated with an ellipsis suffix.
GOAL_MAX_LENGTH = 500

# Shorter budget used when the goal is only shown in monitoring UIs
# (activity monitor, logs) where long text hurts readability.
GOAL_DISPLAY_MAX_LENGTH = 200


class GoalDistiller:
    """
    Distills a clean session goal string.

    Only accepts explicit session_goal strings (e.g. provided by Supervisor).
    Does not attempt to guess or extract goals from arbitrary chat messages.
    """

    @staticmethod
    def from_explicit(
        goal: str | None,
        *,
        max_length: int = GOAL_MAX_LENGTH,
    ) -> str | None:
        """
        Sanitize and truncate an already-known goal string.

        Returns ``None`` if the input is empty/whitespace-only.
        """
        if not goal or not goal.strip():
            return None
        return GoalDistiller._truncate(goal.strip(), max_length)

    @staticmethod
    def for_display(goal: str | None) -> str | None:
        """
        Return a shortened version of the goal suitable for monitoring UIs and logs.
        Uses ``GOAL_DISPLAY_MAX_LENGTH`` (200 chars).
        """
        if not goal:
            return None
        return GoalDistiller._truncate(goal, GOAL_DISPLAY_MAX_LENGTH)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate(text: str, max_length: int) -> str:
        """Truncate ``text`` to ``max_length`` chars, appending '...' if cut."""
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."
