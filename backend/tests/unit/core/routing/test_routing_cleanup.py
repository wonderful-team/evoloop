"""Regression tests for the routing/multi-turn cleanup batch.

Covers:
- ``clear_thread_intent_state_for_threads`` used by WebSocket disconnect
  handlers so a reconnect on the same thread does not pick up the previous
  session's ``previous_intent``.
- ``executor`` still imports cleanly after its ``dispatch_macro`` /
  ``handle_builtin`` dead code was removed.
- ``compound_detector._ACTION_WORDS`` has no duplicate entries (sanity),
  without changing the public detection behaviour.
"""

from __future__ import annotations

import pytest

from app.core.routing import executor
from app.core.routing.compound_detector import _ACTION_WORDS, is_compound_intent
from app.core.routing.conversation_state import (
    clear_thread_intent_state,
    clear_thread_intent_state_for_threads,
    conversation_state,
)


@pytest.fixture(autouse=True)
def _isolate_thread_cache() -> None:
    clear_thread_intent_state()
    yield
    clear_thread_intent_state()


class TestClearThreadIntentStateForThreads:
    def test_clears_listed_threads_only(self) -> None:
        conversation_state.update("t-A", "environment_query", "当前 CPU 是什么型号")
        conversation_state.update("t-B", "worker_task", "写一个知乎爬虫")
        conversation_state.update("t-C", "macro_task", "打开微信")

        clear_thread_intent_state_for_threads(["t-A", "t-C"])

        assert conversation_state.get("t-A") == (None, [])
        assert conversation_state.get("t-B") == ("worker_task", ["写一个知乎爬虫"])
        assert conversation_state.get("t-C") == (None, [])

    def test_empty_list_is_noop(self) -> None:
        conversation_state.update("t-X", "macro_task", "回首页")
        clear_thread_intent_state_for_threads([])
        # No clear happens, intent retained.
        assert conversation_state.get("t-X") == ("macro_task", ["回首页"])

    def test_skips_falsy_thread_ids(self) -> None:
        """Empty / None thread ids must not crash the helper."""
        conversation_state.update("t-Y", "environment_query", "那它的内存呢")
        # Should not raise.
        clear_thread_intent_state_for_threads(["", None, "t-Y", "t-Z"])
        assert conversation_state.get("t-Y") == (None, [])
        assert conversation_state.get("t-Z") == (None, [])

    def test_simulate_ws_disconnect_drops_prior_intent(self) -> None:
        """End-to-end shape: a thread records an intent across a route, then
        a disconnect-style cleanup wipes it. A reconnect on the same thread
        must NOT inherit the previous intent.
        """
        # Cold-start invariant.
        assert conversation_state.get("t-ws-disc") == (None, [])

        # Simulate the route path having recorded an intent.
        conversation_state.update("t-ws-disc", "environment_query", "当前 CPU")
        assert conversation_state.get("t-ws-disc")[0] == "environment_query"

        # WS disconnect cleanup.
        clear_thread_intent_state_for_threads(["t-ws-disc"])

        # Reconnect scenario: previous intent must no longer leak.
        assert conversation_state.get("t-ws-disc") == (None, [])


class TestExecutorDeadCodeRemoved:
    def test_dispatch_macro_removed(self) -> None:
        assert not hasattr(executor, "dispatch_macro"), (
            "executor.dispatch_macro was deleted as dead code; it must not "
            "reappear."
        )

    def test_handle_builtin_removed(self) -> None:
        assert not hasattr(executor, "handle_builtin"), (
            "executor.handle_builtin was deleted as dead code; it must not "
            "reappear."
        )

    def test_macro_timeout_constant_removed(self) -> None:
        assert not hasattr(executor, "_MACRO_TIMEOUT"), (
            "_MACRO_TIMEOUT only fed the deleted dispatch_macro wrapper; it "
            "must not come back."
        )

    def test_live_helpers_still_present(self) -> None:
        """The push_* / handle_navigate helpers that VoicePresenter and the
        agent message pipeline still use must remain after the cleanup.
        """
        assert hasattr(executor, "push_macro_result")
        assert hasattr(executor, "push_local_result")
        assert hasattr(executor, "handle_navigate")
        assert hasattr(executor, "push_tts_text")
        assert hasattr(executor, "maybe_push_tts")


class TestCompoundDetectorDedup:
    def test_action_words_has_no_duplicates(self) -> None:
        seen: set[str] = set()
        dups: list[str] = []
        for word in _ACTION_WORDS:
            if word in seen and word not in dups:
                dups.append(word)
            seen.add(word)
        assert dups == [], f"action_words has duplicates: {dups}"

    @pytest.mark.parametrize(
        "text, expected",
        [
            # Single action -> not compound (must not regress after dedup).
            ("打开微信", False),
            ("静音一下", False),
            # Sequential marker + action word -> compound (unchanged).
            ("打开微信然后静音", True),
            ("打开 Chrome 然后搜索新闻", True),
            # No action word -> not compound.
            ("你好", False),
        ],
    )
    def test_detection_behaviour_unchanged(self, text: str, expected: bool) -> None:
        assert is_compound_intent(text) is expected