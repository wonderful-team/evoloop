"""TraceParser over real recorder-written rows.

Regression guard for the double-encoding bug: recorder endpoints used to
store ``state_snapshot`` as a json.dumps string, and ``_parse_event`` passed
it straight into ``TraceStep.state_context`` (a pydantic model field). The
ValidationError was swallowed by the narrow except and the whole event was
silently dropped from synthesis. With dict storage every recorder source
must parse through.
"""

import pytest

from app.core.learning.trace_parser import TraceParser
from app.infrastructure.database import session_scope
from app.models.learning import TraceEvent


async def _insert_event(**kwargs) -> None:
    async with session_scope() as db:
        db.add(
            TraceEvent(
                member_id=0,
                thread_id="t-parse",
                session_id="s1",
                recording_session_id="s1",
                step_number=kwargs.pop("step_number", 0),
                node_name=kwargs.pop("node_name", "n"),
                event_type=kwargs.pop("event_type", "click"),
                payload=kwargs.pop("payload", {"selector": "#a"}),
                **kwargs,
            )
        )


@pytest.mark.asyncio
async def test_dom_source_event_survives_parse(_real_db):
    await _insert_event(
        source="dom",
        is_human_action=True,
        node_name="dom_recorder",
        state_snapshot={"context": "dom_recorder", "url": "https://x.test/a"},
    )

    seq = await TraceParser("t-parse").parse()

    assert len(seq.steps) == 1
    assert seq.steps[0].state_context.get("url") == "https://x.test/a"


@pytest.mark.asyncio
async def test_mobile_source_event_survives_parse(_real_db):
    await _insert_event(
        source="mobile",
        is_human_action=True,
        event_type="tap",
        state_snapshot={"context": "android_mirror"},
    )

    seq = await TraceParser("t-parse").parse()

    assert len(seq.steps) == 1
    assert seq.steps[0].state_context.get("context") == "android_mirror"


@pytest.mark.asyncio
async def test_global_source_event_unaffected(_real_db):
    """The global-source branch builds state_context itself and never read
    state_snapshot; pinned so the two branches can't silently diverge."""
    await _insert_event(
        source="global",
        is_human_action=True,
        app_name="com.apple.Safari",
        window_title="Safari",
        state_snapshot=None,
    )

    seq = await TraceParser("t-parse").parse()

    assert len(seq.steps) == 1
    assert seq.steps[0].state_context.get("app_name") == "com.apple.Safari"
