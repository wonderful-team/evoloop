"""
GoalDistiller — Goal extraction and normalization utility.

Provides a single, testable entry point for deriving a clean ``session_goal``
string from any combination of inputs (explicit string, LangChain messages,
raw dicts).

Design rules:
- Pure / stateless: no DB calls, no LLM calls, no side effects.
- Returns a sanitized, truncated string that is safe for storage and display.
- Callers (dispatch.py, BackgroundAgent) delegate here instead of inlining
  ad-hoc truncation and extraction logic.
"""

import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

logger = logging.getLogger(__name__)

# Maximum character length for a stored/displayed session goal.
# Longer text is truncated with an ellipsis suffix.
GOAL_MAX_LENGTH = 500

# Shorter budget used when the goal is only shown in monitoring UIs
# (activity monitor, logs) where long text hurts readability.
GOAL_DISPLAY_MAX_LENGTH = 200


class GoalDistiller:
    """
    Distills a clean session goal string from heterogeneous input sources.

    Priority order when multiple sources are available:
    1. Explicit ``session_goal`` string (already distilled by the caller)
    2. First HumanMessage in a LangChain message list
    3. First human-role entry in a raw dict list
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
    def from_messages(
        messages: list[BaseMessage] | list[dict[str, Any]],
        *,
        max_length: int = GOAL_MAX_LENGTH,
    ) -> str | None:
        """
        Extract the first human message content and use it as the session goal.

        Handles both LangChain ``BaseMessage`` objects and raw dicts with a
        ``role``/``content`` structure (as produced by ``EvoMessageConverter``).

        Returns ``None`` when no suitable human message is found.
        """
        for msg in messages:
            content = GoalDistiller._extract_human_content(msg)
            if content:
                return GoalDistiller._truncate(content, max_length)
        return None

    @staticmethod
    def resolve(
        explicit_goal: str | None,
        messages: list[BaseMessage] | list[dict[str, Any]] | None = None,
        *,
        max_length: int = GOAL_MAX_LENGTH,
    ) -> str | None:
        """
        Resolve the best available session goal using priority order.

        1. ``explicit_goal`` (if non-empty after stripping)
        2. First human message in ``messages`` (fallback)
        3. ``None`` (no goal could be derived)

        Args:
            explicit_goal: Pre-computed goal string, e.g. from API input.
            messages: LangChain BaseMessage list or raw dict list to fall back to.
            max_length: Maximum character length before truncation.

        Returns:
            Sanitized, truncated session goal string, or ``None``.
        """
        # Priority 1: explicit goal
        candidate = GoalDistiller.from_explicit(explicit_goal, max_length=max_length)
        if candidate:
            return candidate

        # Priority 2: first human message
        if messages:
            candidate = GoalDistiller.from_messages(messages, max_length=max_length)
            if candidate:
                logger.debug(
                    f"[GoalDistiller] Derived session_goal from first human message "
                    f"({len(candidate)} chars)"
                )
                return candidate

        return None

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

    @staticmethod
    def _extract_human_content(
        msg: BaseMessage | dict[str, Any],
    ) -> str | None:
        """
        Extract text content from a human/user message.

        Returns ``None`` for non-human messages or messages with empty content.
        """
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, list):
                # Multimodal: join all text blocks
                parts = [
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                    if not isinstance(block, dict) or block.get("type") != "image_url"
                ]
                content = " ".join(p for p in parts if p).strip()
            return str(content).strip() or None

        if isinstance(msg, dict):
            role = msg.get("role") or msg.get("type", "")
            if role not in ("human", "user"):
                return None
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = [
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                    if not isinstance(block, dict) or block.get("type") != "image_url"
                ]
                content = " ".join(p for p in parts if p).strip()
            return str(content).strip() or None

        return None
