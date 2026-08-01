"""Per-thread conversation state and anaphora detection for L0 routing.

This module isolates the mutable multi-turn state that used to live directly in
``command_router.py``.  It is intentionally a lightweight in-memory cache: the
GIL makes dict operations atomic, and the async event loop is single-threaded,
so a simple dict is sufficient without an explicit lock.
"""

from __future__ import annotations

import re

from app.core.routing.schemas import IntentHint

# Maximum number of recent user turns retained per thread for L0 context.
_SESSION_HISTORY_LIMIT = 6

# Anaphora / coreference markers. The single source of truth for "this turn
# depends on prior context" detection shared by ``ConversationState.has_anaphora``
# and ``context_assembler._needs_context``.
#
# Covers the union of both earlier hand-written regexes so detection stays
# consistent across layers:
#   - bare 它/他/她 (+ plural/possessive variants: 它们/他/她的)
#   - 这[个件] / 那[个件]
#   - 刚才 / 之前 / 上次 / 前面
#   - 这些 / 那些
# "应该" (should) contains 该 but starts with 应, and is intentionally excluded.
_ANAPHORA_RE = re.compile(
    r"(?:它(?:们|的)?|他(?:们|的)?|她(?:们|的)?"
    r"|这[个件]|那[个件]|这些|那些"
    r"|刚才|之前|上次|前面)"
)


class ConversationState:
    """In-memory per-thread L0 state for multi-turn coreference support."""

    def __init__(self) -> None:
        # Keys are thread_id; values are (previous_intent, [recent user texts]).
        self._state: dict[str, tuple[str | None, list[str]]] = {}

    def get(self, thread_id: str) -> tuple[str | None, list[str]]:
        """Return ``(previous_intent, session_history)`` for the thread."""
        return self._state.get(thread_id, (None, []))

    def update(self, thread_id: str, intent: str | None, text: str) -> None:
        """Record the resolved intent and append the user text to history."""
        if not thread_id:
            return
        prev_intent, history = self._state.get(thread_id, (None, []))
        new_history = (history + [text])[-_SESSION_HISTORY_LIMIT:]
        self._state[thread_id] = (intent, new_history)

    def clear(self, thread_id: str | None = None) -> None:
        """Clear a single thread, or all threads when ``thread_id`` is None."""
        if thread_id is None:
            self._state.clear()
        else:
            self._state.pop(thread_id, None)

    @staticmethod
    def has_anaphora(text: str) -> bool:
        """Return True when ``text`` contains an anaphora marker."""
        return bool(_ANAPHORA_RE.search(text))

    @staticmethod
    def apply_anaphora_boost(
        hint: IntentHint,
        text: str,
        has_prior_context: bool,
    ) -> IntentHint:
        """Add ``Memory`` to ``suggested_modules`` for cross-turn anaphora.

        When the current turn references a prior entity (``它/这个/刚才``) and
        the thread has recorded a prior turn, we ensure memory recall is
        available to the hydrator even for intents that normally skip it
        (e.g. ``environment_query`` with "那它的内存呢").  A new ``IntentHint``
        instance is returned so the input model is not mutated.
        """
        if not has_prior_context:
            return hint
        if "Memory" in hint.suggested_modules:
            return hint
        if not ConversationState.has_anaphora(text):
            return hint

        new_modules = list(hint.suggested_modules) + ["Memory"]
        new_reason = (hint.reason or "") + " +anaphora"
        return hint.model_copy(
            update={"suggested_modules": new_modules, "reason": new_reason}
        )


# Module singleton used by the command router and tests.
conversation_state = ConversationState()


def _get_thread_intent_state(thread_id: str) -> tuple[str | None, list[str]]:
    """Return ``(previous_intent, session_history)`` for the given thread.

    Returns ``(None, [])`` when the thread has no recorded prior turn yet.
    """
    return conversation_state.get(thread_id)


def _update_thread_intent_state(
    thread_id: str, intent: str | None, text: str
) -> None:
    """Record the resolved intent and append the user text to the rolling history."""
    conversation_state.update(thread_id, intent, text)


def clear_thread_intent_state(thread_id: str | None = None) -> None:
    """Test/state helper: clear the thread intent cache.

    Pass a thread_id to clear a single thread; pass None to clear everything.
    """
    conversation_state.clear(thread_id)


def clear_thread_intent_state_for_threads(thread_ids: list[str]) -> None:
    """Clear multi-turn L0 state for all threads in ``thread_ids``.

    Used by WebSocket disconnect handlers so a reconnect or a later session on
    one of the connection's threads starts cold: no stale ``previous_intent``
    leaks into the new session (see routing §5.9 multi-turn coreference and
    the lesson from the deleted ``session_frame.py``).
    """
    for tid in thread_ids:
        if tid:
            conversation_state.clear(tid)


__all__ = [
    "_ANAPHORA_RE",
    "_SESSION_HISTORY_LIMIT",
    "ConversationState",
    "conversation_state",
    "_get_thread_intent_state",
    "_update_thread_intent_state",
    "clear_thread_intent_state",
    "clear_thread_intent_state_for_threads",
]
