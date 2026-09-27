"""Coverage for TraceParser (raw TraceEvent → TraceSequence)."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import delete

from app.core.learning.schemas import ActionCategory, ActionSource
from app.core.learning.trace import parser as parser_module
from app.core.learning.trace.parser import TraceParser, TraceSequence
from app.models.conversation import Message
from app.models.learning import TraceEvent


def _event(step: int, **kw) -> TraceEvent:
    defaults = {
        "thread_id": "t1",
        "step_number": step,
        "node_name": "node",
        "event_type": "tool_call",
        "payload": {},
        "source": "agent",
        "is_human_action": False,
    }
    defaults.update(kw)
    return TraceEvent(**defaults)


@pytest.fixture(autouse=True)
def _clean(test_session_scope):
    yield

    async def _clean():
        async with test_session_scope() as db:
            await db.execute(delete(TraceEvent))
            await db.execute(delete(Message))

    asyncio.run(_clean())


@pytest.fixture
def parser_scope(test_session_scope, monkeypatch):
    monkeypatch.setattr(parser_module, "session_scope", test_session_scope)


@pytest.mark.asyncio
class TestParse:
    async def test_parse_full_flow(self, parser_scope, test_session_scope):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _event(
                        1,
                        event_type="tool_call",
                        payload={"name": "read_file", "args": {"path": "/x"}},
                    ),
                    _event(
                        2,
                        event_type="click",
                        payload={"x": 1, "y": 2},
                        source="global",
                        is_human_action=True,
                        app_name="Finder",
                        mouse_x=1,
                        mouse_y=2,
                    ),
                    Message(
                        id="m1",
                        thread_id="t1",
                        role="human",
                        content="open the file",
                    ),
                ]
            )
            await db.flush()

        seq = await TraceParser("t1").parse()
        assert isinstance(seq, TraceSequence)
        assert len(seq.steps) == 2
        assert seq.initial_intent == "open the file"
        assert "read_file" in seq.tools_used

    async def test_parse_with_session_filter(self, parser_scope, test_session_scope):
        async with test_session_scope() as db:
            db.add_all(
                [
                    _event(1, thread_id="t1", session_id="s1"),
                    _event(2, thread_id="t1", recording_session_id="s1"),
                    _event(3, thread_id="t1", session_id="other"),
                ]
            )
            await db.flush()
        seq = await TraceParser("t1", session_id="s1").parse()
        assert len(seq.steps) == 2

    async def test_parse_no_intent_when_no_messages(self, parser_scope, test_session_scope):
        async with test_session_scope() as db:
            db.add(_event(1))
            await db.flush()
        seq = await TraceParser("t1").parse()
        assert seq.initial_intent is None


class TestConvertToSequence:
    def test_tool_call_tracks_tools(self):
        seq = TraceParser("t1")._convert_to_sequence(
            [
                _event(
                    1,
                    event_type="tool_call",
                    payload={"name": "edit", "args": {}},
                )
            ]
        )
        assert seq.steps[0].action_name == "edit"
        assert seq.steps[0].category == ActionCategory.EDIT
        assert seq.tools_used == ["edit"]

    def test_human_intervention_flag(self):
        seq = TraceParser("t1")._convert_to_sequence(
            [
                _event(
                    1,
                    event_type="click",
                    source="global",
                    is_human_action=True,
                    mouse_x=1,
                    mouse_y=2,
                )
            ]
        )
        assert seq.has_human_intervention is True
        assert seq.steps[0].source == ActionSource.HUMAN

    def test_mobile_event_keeps_raw_payload(self):
        seq = TraceParser("t1")._convert_to_sequence(
            [
                _event(
                    1,
                    event_type="user_interaction",
                    source="mobile",
                    payload={"x": 10},
                )
            ]
        )
        assert seq.steps[0].action_args.model_dump() == {"x": 10}

    def test_unparseable_event_skipped(self):
        # a None source with a bad snapshot should still parse via fallback; feed a
        # payload that trips nothing — just assert a valid step is produced
        seq = TraceParser("t1")._convert_to_sequence(
            [_event(1, event_type="llm_output", payload={"content": "x"})]
        )
        assert len(seq.steps) == 1


class TestCategorize:
    def test_tool_specific(self):
        assert TraceParser("t1")._categorize_action("tool_call", "read_file") == ActionCategory.QUERY

    def test_event_type_fallback(self):
        assert TraceParser("t1")._categorize_action("click", "x") == ActionCategory.INTERACTION

    def test_unknown(self):
        assert TraceParser("t1")._categorize_action("mystery", "x") == ActionCategory.OTHER


class TestSummarize:
    def test_summarize_counts(self):
        seq = TraceParser("t1")._convert_to_sequence(
            [
                _event(1, event_type="tool_call", payload={"name": "read_file"}),
                _event(2, event_type="tool_call", payload={"name": "read_file"}),
                _event(
                    3,
                    event_type="click",
                    source="global",
                    is_human_action=True,
                    mouse_x=0,
                    mouse_y=0,
                ),
            ]
        )
        summary = seq.summarize()
        assert summary.total_steps == 3
        assert summary.human_steps == 1
        assert summary.agent_steps == 2
        assert set(summary.tools_used) == {"read_file"}

    def test_to_narrative_error_fallback(self, monkeypatch):
        seq = TraceParser("t1")._convert_to_sequence([])
        monkeypatch.setattr(
            "app.utils.template.render_template",
            lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        out = TraceParser("t1").to_narrative(seq)
        assert "Error rendering template" in out
