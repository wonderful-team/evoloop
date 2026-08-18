"""Per-thread conversation state and anaphora detection for L0 routing.

This module isolates the mutable multi-turn state that used to live directly in
``command_router.py``.  It is intentionally a lightweight in-memory cache: the
GIL makes dict operations atomic, and the async event loop is single-threaded,
so a simple dict is sufficient without an explicit lock.
"""

from __future__ import annotations

import re

from app.core.routing.device_kind import DeviceKind
from app.core.routing.routing_data import get_store
from app.core.routing.schemas import IntentHint

# Maximum number of recent user turns retained per thread for L0 context.
_SESSION_HISTORY_LIMIT = 6

# Anaphora / coreference markers. The single source of truth for "this turn
# depends on prior context" detection shared by ``ConversationState.has_anaphora``
# and ``context_assembler._needs_context``.
#
# The marker word list is data-driven (templates.yaml ``anaphora_markers``).
# The regex is compiled lazily and cached against the current markers, so a
# runtime LANGUAGE switch (which reloads the routing store) transparently
# recompiles with the new language's markers.  Longest-first ordering makes
# "它们" win over "它" at the same position (boolean results are unchanged).
# "应该" (should) contains 该 but is a full marker "应该" only — it is not
# listed as a marker, so it never matches.
#
# Latin-script markers (English: "he", "it", "this" ...) are matched with
# ``\b`` word boundaries so ordinary words like "where" (contains "he") or
# "visit" (contains "it") are not flagged as anaphora.  CJK markers have no
# word boundaries and are matched as-is.

_CJK_RE = re.compile(r"[\u3000-\u9fff\uf900-\ufaff]")


def _escape_marker(marker: str) -> str:
    """Escape a marker; wrap Latin-script markers with ``\\b`` boundaries."""
    if _CJK_RE.search(marker):
        return re.escape(marker)
    return rf"\b{re.escape(marker)}\b"


class _AnaphoraMatcher:
    """Cached anaphora regex that recompiles when the routing store's markers
    change (e.g. after a runtime LANGUAGE switch reloads the store)."""

    def __init__(self) -> None:
        self._markers: tuple[str, ...] | None = None
        self._re: re.Pattern | None = None

    def search(self, text: str):
        markers = tuple(get_store().anaphora_markers)
        if markers != self._markers:
            self._markers = markers
            self._re = re.compile(
                "|".join(_escape_marker(m) for m in sorted(markers, key=len, reverse=True))
                or r"(?!)",
                re.IGNORECASE,
            )
        return self._re.search(text)


_ANAPHORA_RE = _AnaphoraMatcher()


class ConversationState:
    """In-memory per-thread L0 context shared by the L0 and L1 layers.

    Stores the resolved intent label + rolling user history (already used by
        ``context_assembler`` for the L1 anaphora input) and, in addition, the
        last-seen **device context** (``DeviceKind``) used by the L0 macro
        template layer for device-aware disambiguation:

            user:  手机播放音乐   -> device becomes DeviceKind.PHONE
            user:  切歌          -> template hit is desktop 下一曲; the device
                                   context redirects it to the phone twin.
    """

    def __init__(self) -> None:
        # Keys are thread_id; values are (previous_text, [recent user texts]).
        self._state: dict[str, tuple[str | None, list[str]]] = {}
        # Keys are thread_id; values are the resolved device kind (DeviceKind).
        self._device: dict[str, DeviceKind] = {}
        # Keys are thread_id; values are the most recent L0 macro execution
        # result summary (e.g. "已跳转到商城后台添加商品页"), used to give the
        # Agent context about what an L0 macro just did on the next turn.
        self._last_macro_result: dict[str, str] = {}

    def get(self, thread_id: str) -> tuple[str | None, list[str]]:
        """Return ``(previous_intent, session_history)`` for the thread."""
        return self._state.get(thread_id, (None, []))

    def update(self, thread_id: str, intent: str | None, text: str) -> None:
        """Record the resolved intent and append the user text to history."""
        if not thread_id:
            return
        prev_intent, history = self._state.get(thread_id, (None, []))
        self._state[thread_id] = (
            intent,
            history[-_SESSION_HISTORY_LIMIT + 1 :] + [text],
        )

    def set_device(self, thread_id: str, device: DeviceKind | None) -> None:
        """Remember the device kind of the last macro action."""
        if not thread_id:
            return
        if device is None:
            self._device.pop(thread_id, None)
        else:
            self._device[thread_id] = device

    def get_device(self, thread_id: str) -> DeviceKind | None:
        """Return the device context for the thread, or ``None`` when absent."""
        return self._device.get(thread_id) if thread_id else None

    def set_last_macro_result(self, thread_id: str, summary: str) -> None:
        """Remember the summary of the most recent L0 macro execution."""
        if not thread_id:
            return
        self._last_macro_result[thread_id] = summary

    def get_last_macro_result(self, thread_id: str) -> str | None:
        """Return the most recent L0 macro result summary, or ``None``."""
        return self._last_macro_result.get(thread_id) if thread_id else None

    def clear(self, thread_id: str | None = None) -> None:
        """Clear a single thread, or all threads when ``thread_id`` is None."""
        if thread_id is None:
            self._state.clear()
            self._device.clear()
            self._last_macro_result.clear()
        else:
            self._state.pop(thread_id, None)
            self._device.pop(thread_id, None)
            self._last_macro_result.pop(thread_id, None)

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


def _update_thread_intent_state(thread_id: str, intent: str | None, text: str) -> None:
    """Record the resolved intent and append the user text to the rolling history."""
    conversation_state.update(thread_id, intent, text)


def _get_thread_device_context(thread_id: str) -> DeviceKind | None:
    """Return the device context kind for the thread.

    Used by the L0 macro template layer to disambiguate device-ambiguous
    utterances (e.g. "切歌" right after a phone media macro).
    """
    return conversation_state.get_device(thread_id)


def _update_thread_device_context(thread_id: str, device: DeviceKind | None) -> None:
    """Record the resolved device context kind for the thread."""
    conversation_state.set_device(thread_id, device)


def _get_thread_last_macro_result(thread_id: str) -> str | None:
    """Return the most recent L0 macro result summary for the thread."""
    return conversation_state.get_last_macro_result(thread_id)


def _set_thread_last_macro_result(thread_id: str, summary: str) -> None:
    """Record the summary of the most recent L0 macro execution for the thread."""
    conversation_state.set_last_macro_result(thread_id, summary)


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
    "_get_thread_intent_state",
    "_update_thread_intent_state",
    "_get_thread_last_macro_result",
    "_set_thread_last_macro_result",
    "clear_thread_intent_state_for_threads",
]
