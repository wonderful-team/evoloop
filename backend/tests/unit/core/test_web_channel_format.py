"""Tests for WebChannel.format_event_for_frontend data-type compatibility.

Verifies that events whose ``data`` is a plain dict (e.g.
``StateChangedEvent`` sets ``self.data = {...}`` in ``model_post_init``)
serialize without ``AttributeError: 'dict' object has no attribute
'model_dump'``.
"""


from app.core.channel.output.web_channel import format_event_for_frontend
from app.core.events.schemas.lifecycle import StateChangedEvent


def test_state_changed_event_with_dict_data():
    """StateChangedEvent.data is a dict → serializes without crash."""
    event = StateChangedEvent(
        source="SharedState",
        key="agent_name",
        old_value="",
        new_value="小明",
        thread_id="t-1",
    )
    payload = format_event_for_frontend(event)
    assert payload["type"] == "system_event"
    assert payload["data"] == {
        "key": "agent_name",
        "old_value": "",
        "new_value": "小明",
    }
    assert payload["event"] == "system.state_changed"
