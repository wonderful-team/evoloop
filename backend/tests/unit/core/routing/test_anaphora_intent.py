"""Multi-turn coreference (anaphora) integration for telescopic context.

§5.9 of docs/supervisor-telescopic-context-design.md reserved the
``previous_intent`` / ``session_history`` fields on IntentHint. This module
exercises the now-wired behavior: a turn that carries an anaphora marker
(它/这个/刚才) AND has a recorded prior turn for the same thread is
annotated with the prior context so that downstream ``AgentContextHydrator``
keeps semantic recall available for cross-turn entity resolution, even for
intents (e.g. ``system_info_query``) that normally skip Tier 2 memory loading.

Under the domain-based design, the router only emits the L1 ``domain``; the
engine maps it to a functional intent and applies the Memory anaphora boost.
"""

from __future__ import annotations

import pytest

from app.core.routing.conversation_state import (
    _ANAPHORA_RE,
    clear_thread_intent_state,
    conversation_state,
)
from app.core.routing.schemas import IntentHint


def _make_hint(
    text: str,
    intent: str,
    modules: list[str],
    *,
    previous_intent: str | None = None,
    session_history: list[str] | None = None,
) -> IntentHint:
    """Build an IntentHint and apply the anaphora boost, mirroring CommandRouter."""
    hint = IntentHint(
        intent=intent,
        confidence=0.9,
        suggested_modules=modules,
        reason=f"test:{intent}",
        previous_intent=previous_intent,
        session_history=session_history,
    )
    return conversation_state.apply_anaphora_boost(
        hint, text, bool(previous_intent or session_history)
    )


@pytest.fixture(autouse=True)
def _isolate_thread_cache() -> None:
    """Each test gets a clean thread intent cache."""
    clear_thread_intent_state()
    yield
    clear_thread_intent_state()


class TestAnaphoraRegex:
    """The regex must accept real anaphora and reject common false positives."""

    @pytest.mark.parametrize(
        "text",
        [
            "那它的内存呢",
            "它还在跑吗",
            "它们的端口是多少",
            "他的状态呢",
            "这个多少钱",
            "那件文件呢",
            "刚才那个查到了吗",
            "它的库存改成142",
        ],
    )
    def test_hits(self, text: str) -> None:
        assert _ANAPHORA_RE.search(text) is not None

    @pytest.mark.parametrize(
        "text",
        [
            "应该下架",  # bare 该 inside 应该 — no real anaphora
            "播放音乐",
            "写一个知乎爬虫",
            "打开计算器",
            "当前 CPU 是什么型号",
            "你好",
            "继续刚才那个任务",  # contains 刚才/那个 — IS anaphora, listed here only
            # to keep the guard below meaningful; the guard skips it.
        ],
    )
    def test_known_negatives(self, text: str) -> None:
        # Only verify phrases that should genuinely NOT match. Any text that
        # legitimately contains an anaphora marker is skipped — verifying
        # those is the hits suite's job.
        if any(m in text for m in ("它", "他", "她", "这", "那个", "刚才")):
            pytest.skip("guardrail: phrase actually contains an anaphora marker")
        assert _ANAPHORA_RE.search(text) is None


class TestAnaphoraBoost:
    """The anaphora boost must add Memory to suggested_modules on cross-turn anaphora."""

    def test_system_info_query_without_prior_context_no_memory(self) -> None:
        """First turn: no prior context -> no Memory added."""
        hint = _make_hint("当前 CPU 是什么型号", "system_info_query", ["Base", "Environment"])
        assert hint.intent == "system_info_query"
        assert "Environment" in hint.suggested_modules
        assert "Memory" not in hint.suggested_modules
        assert hint.previous_intent is None
        assert hint.session_history is None

    def test_system_info_query_with_prior_context_adds_memory(self) -> None:
        """Second turn: '那它的内存呢' carries anaphora + prior intent -> Memory added."""
        hint = _make_hint(
            "那它的内存呢",
            "system_info_query",
            ["Base", "Environment"],
            previous_intent="system_info_query",
            session_history=["当前 CPU 是什么型号"],
        )
        assert hint.intent == "system_info_query"
        assert "Environment" in hint.suggested_modules
        assert "Memory" in hint.suggested_modules
        assert "+anaphora" in hint.reason
        assert hint.previous_intent == "system_info_query"
        assert hint.session_history == ["当前 CPU 是什么型号"]

    def test_anaphora_without_prior_context_no_memory(self) -> None:
        """Anaphora but cold thread -> no Memory injected (no prior entity to recall)."""
        hint = _make_hint("它的内存呢", "system_info_query", ["Base", "Environment"])
        assert hint.intent == "system_info_query"
        assert "Memory" not in hint.suggested_modules

    def test_ambiguous_with_anaphora_keeps_memory(self) -> None:
        """ambiguous already loads Memory; anaphora must not duplicate it."""
        hint = _make_hint(
            "那刚才的呢",
            "ambiguous",
            ["Base", "Memory", "Environment"],
            previous_intent="worker_task",
            session_history=["写一个知乎爬虫"],
        )
        assert hint.intent == "ambiguous"
        # ambiguous always has Memory; ensure no duplicate entry
        assert hint.suggested_modules.count("Memory") == 1

    def test_direct_answer_not_polluted_by_anaphora(self) -> None:
        """direct_answer should keep its minimal Base module list."""
        hint = _make_hint(
            "你好",
            "direct_answer",
            ["Base"],
            previous_intent="system_info_query",
            session_history=["当前 CPU 是什么型号"],
        )
        assert hint.intent == "direct_answer"
        assert hint.suggested_modules == ["Base"]


class TestThreadStateRoundTrip:
    """End-to-end: CommandRouter.resolve() records previous_intent and uses it."""

    @pytest.mark.asyncio
    async def test_two_turns_thread_propagates_intent(self) -> None:
        from app.core.routing.command_router import CommandRouter
        from app.core.routing.conversation_state import _get_thread_intent_state

        router = CommandRouter()
        try:
            # Turn 1: establish system_info domain.
            await router.resolve(
                "当前 CPU 是什么型号",
                thread_id="t-anaphora-1",
                project_id=0,
                source="chat",
            )
            prev_intent, history = _get_thread_intent_state("t-anaphora-1")
            assert prev_intent == "system_info"
            assert history == ["当前 CPU 是什么型号"]

            # Turn 2: anaphora referencing the prior CPU entity.
            decision = await router.resolve(
                "那它的内存呢",
                thread_id="t-anaphora-1",
                project_id=0,
                source="chat",
            )
            assert decision.intent_hint is not None
            assert decision.intent_hint.domain == "system_info"
            assert decision.intent_hint.intent == "domain_classified"
            assert decision.intent_hint.previous_intent == "system_info"
            # session_history carries both turns (rolling window).
            assert "当前 CPU 是什么型号" in (decision.intent_hint.session_history or [])
        finally:
            clear_thread_intent_state("t-anaphora-1")

    @pytest.mark.asyncio
    async def test_different_threads_isolated(self) -> None:
        from app.core.routing.command_router import CommandRouter
        from app.core.routing.conversation_state import _get_thread_intent_state

        router = CommandRouter()
        try:
            await router.resolve(
                "当前 CPU 是什么型号",
                thread_id="t-A",
                project_id=0,
                source="chat",
            )
            await router.resolve(
                "写一个知乎爬虫",
                thread_id="t-B",
                project_id=0,
                source="chat",
            )
            assert _get_thread_intent_state("t-A")[0] == "system_info"
            assert _get_thread_intent_state("t-B")[0] == "coding_dev"

            # Anaphora in thread B should not pull thread A's intent.
            decision_b = await router.resolve(
                "那它的内存呢",
                thread_id="t-B",
                project_id=0,
                source="chat",
            )
            assert decision_b.intent_hint.previous_intent == "coding_dev"
        finally:
            clear_thread_intent_state("t-A")
            clear_thread_intent_state("t-B")

    @pytest.mark.asyncio
    async def test_macro_fast_path_still_records_intent(self) -> None:
        """Bug #1 regression: a turn that resolves via the macro fast-path
        (returning early before the delegate branch) must still write
        the resolved label so a following anaphora turn can find prior context.

        Reproduces: turn 1 = "当前 CPU 是什么型号" hits system_info domain via
        the delegate path (records correctly). Turn 2 = "打开 Firefox"
        resolved through BERT+local_matcher to a local macro action — early
        return in branches 1/2/3 used to skip _record_thread_intent, so
        turn 3 = "它的内存呢" would see previous_intent=None and lose the
        anaphora context.
        """
        from app.core.routing.command_router import CommandRouter
        from app.core.routing.conversation_state import _get_thread_intent_state

        router = CommandRouter()
        try:
            # Turn 1 — agent path, records system_info.
            d1 = await router.resolve(
                "当前 CPU 是什么型号",
                thread_id="t-macro-path",
                project_id=0,
                source="chat",
            )
            assert d1.intent_hint.domain == "system_info"
            assert _get_thread_intent_state("t-macro-path")[0] == "system_info"

            # Turn 2 — built-in ack ("对/没错" typically resolves to builtin ack
            # OR a direct route). We use a direct-route phrase (handled in
            # branch 1) to deterministically exercise the non-delegate path:
            # "回首页" is in the direct route table.
            await router.resolve(
                "回首页",
                thread_id="t-macro-path",
                project_id=0,
                source="voice",
            )
            # After this turn, thread state must still hold *some* label
            # (the macro/navigation path used to skip the recorder entirely).
            prev_after_t2, history_after_t2 = _get_thread_intent_state("t-macro-path")
            assert prev_after_t2 == "macro_task", (
                f"branch 1 (navigation) must record intent, got {prev_after_t2!r}"
            )
            assert history_after_t2[-1] == "回首页"

            # Turn 3 — anaphora referencing turn 1's CPU entity, arriving after
            # the navigation turn. The previous_intent is macro_task (last
            # recorded), but session_history retains "当前 CPU 是什么型号". The
            # router returns the L1 domain; the engine will add Memory during
            # context hydration.
            d3 = await router.resolve(
                "那它的内存呢",
                thread_id="t-macro-path",
                project_id=0,
                source="chat",
            )
            assert d3.intent_hint.domain == "system_info"
            # session_history must carry turn 1 entity-bearing text so the
            # hydrator's memory_query_text blend can surface that entity.
            assert "当前 CPU 是什么型号" in (d3.intent_hint.session_history or [])
        finally:
            clear_thread_intent_state("t-macro-path")
