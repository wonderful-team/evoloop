"""Coverage for MacroCreatorService: replayability eligibility and the early
returns of create_macro_from_trace."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.learning.macro.creator import MacroCreatorService
from app.models.conversation import AgentActivity
from app.models.learning import TraceEvent
from app.models.macro import Macro


def _build_trace(thread_id: str, event_type: str = "click", **kw) -> TraceEvent:
    return TraceEvent(
        thread_id=thread_id,
        step_number=1,
        node_name="browser_interaction",
        event_type=event_type,
        payload={},
        **kw,
    )


@pytest.fixture(autouse=True)
def _clean_db(test_session_scope):
    yield
    from sqlalchemy import delete

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(TraceEvent))
            await db.execute(delete(Macro))

    asyncio.run(_clean())


@pytest.mark.asyncio
class TestIsEligible:
    async def test_replayable_trace_eligible(self, test_session_scope, monkeypatch):
        monkeypatch.setattr(
            "app.core.learning.macro.creator.session_scope",
            test_session_scope,
        )
        async with test_session_scope() as db:
            db.add(_build_trace("t1", event_type="click"))
            await db.flush()
        assert await MacroCreatorService.is_eligible("t1") is True

    async def test_only_excluded_events_not_eligible(self, test_session_scope, monkeypatch):
        monkeypatch.setattr(
            "app.core.learning.macro.creator.session_scope",
            test_session_scope,
        )
        async with test_session_scope() as db:
            db.add(_build_trace("t2", event_type="llm_output"))
            await db.flush()
        assert await MacroCreatorService.is_eligible("t2") is False


@pytest.mark.asyncio
class TestCreateFromTrace:
    async def test_disabled_returns_none(self, monkeypatch):
        monkeypatch.setattr(
            "app.core.learning.macro.creator.settings.AUTO_MACRO_CREATION_ENABLED",
            False,
        )
        assert await MacroCreatorService.create_macro_from_trace("t3") is None

    async def test_missing_activity_returns_none(self, test_session_scope, monkeypatch):
        monkeypatch.setattr(
            "app.core.learning.macro.creator.settings.AUTO_MACRO_CREATION_ENABLED",
            True,
        )
        monkeypatch.setattr(
            "app.core.learning.macro.creator.session_scope",
            test_session_scope,
        )
        assert await MacroCreatorService.create_macro_from_trace("no-such-thread") is None

    async def test_non_completed_returns_none(self, test_session_scope, monkeypatch):
        monkeypatch.setattr(
            "app.core.learning.macro.creator.settings.AUTO_MACRO_CREATION_ENABLED",
            True,
        )
        monkeypatch.setattr(
            "app.core.learning.macro.creator.session_scope",
            test_session_scope,
        )
        async with test_session_scope() as db:
            db.add(
                AgentActivity(
                    thread_id="t4",
                    final_outcome="FAILED",
                    macro_creation_eligible=True,
                )
            )
            await db.flush()
        assert await MacroCreatorService.create_macro_from_trace("t4") is None

    async def test_not_eligible_activity_returns_none(self, test_session_scope, monkeypatch):
        monkeypatch.setattr(
            "app.core.learning.macro.creator.settings.AUTO_MACRO_CREATION_ENABLED",
            True,
        )
        monkeypatch.setattr(
            "app.core.learning.macro.creator.session_scope",
            test_session_scope,
        )
        async with test_session_scope() as db:
            db.add(
                AgentActivity(
                    thread_id="t5",
                    final_outcome="COMPLETED",
                    macro_creation_eligible=False,
                )
            )
            await db.flush()
        assert await MacroCreatorService.create_macro_from_trace("t5") is None


@pytest.mark.asyncio
class TestCreateFromTraceSuccess:
    async def test_creates_macro(self, test_session_scope, monkeypatch):
        from types import SimpleNamespace

        import app.core.learning.macro.compiler as comp_mod
        import app.core.learning.macro.creator as mcs
        import app.core.learning.macro.lifecycle as lc_mod
        import app.core.learning.trace.parser as tp_mod
        import app.core.learning.workflow_synthesizer as ws_mod

        monkeypatch.setattr(
            "app.core.learning.macro.creator.settings.AUTO_MACRO_CREATION_ENABLED",
            True,
        )
        monkeypatch.setattr(
            mcs, "session_scope", test_session_scope
        )
        async with test_session_scope() as db:
            db.add(
                AgentActivity(
                    thread_id="t-ok", final_outcome="COMPLETED", macro_creation_eligible=True
                )
            )
            await db.flush()

        # mock the synthesis chain
        monkeypatch.setattr(
            tp_mod,
            "TraceParser",
            lambda tid: SimpleNamespace(
                parse=AsyncMock(return_value=SimpleNamespace(steps=[{"type": "action"}]))
            ),
        )
        monkeypatch.setattr(
            comp_mod,
            "MacroScriptCompiler",
            lambda: SimpleNamespace(
                compile=lambda seq: SimpleNamespace(
                    steps=[1], to_yaml=lambda: "yaml: []"
                )
            ),
        )
        monkeypatch.setattr(
            ws_mod,
            "WorkflowSynthesizer",
            lambda *a, **k: SimpleNamespace(
                synthesize=AsyncMock(
                    return_value=SimpleNamespace(
                        macro=SimpleNamespace(
                            name="gen-macro",
                            description="d",
                            trigger_patterns=["t"],
                            parameters=[],
                            namespace="misc",
                        )
                    )
                )
            ),
        )
        created = SimpleNamespace(id=77)
        monkeypatch.setattr(
            lc_mod,
            "create_macro_from_synthesis",
            AsyncMock(return_value=created),
        )

        macro = await mcs.MacroCreatorService.create_macro_from_trace("t-ok", member_id=3)
        assert macro is not None
        lc_mod.create_macro_from_synthesis.assert_awaited_once()
        kwargs = lc_mod.create_macro_from_synthesis.await_args.kwargs
        assert kwargs["name"] == "gen-macro"
        assert kwargs["member_id"] == 3
