"""web_channel.format_event_for_frontend — SystemLogEvent mapping.

The macro step feed (macro_thought) travels as SystemLogEvent; the frontend
per-thread SSE consumer needs thread_id in the payload to attribute steps to
the right run.
"""

from app.core.channel.output.web_channel import format_event_for_frontend
from app.core.monitoring.event import SystemLogEvent


def test_system_log_event_carries_thread_id():
    event = SystemLogEvent(
        thread_id="t-42",
        log_type="macro_thought",
        log_data={"text": "Step 1: open app"},
    )

    formatted = format_event_for_frontend(event)

    assert formatted["type"] == "system_log"
    assert formatted["event"] == "macro_thought"
    assert formatted["data"] == {"text": "Step 1: open app"}
    assert formatted["thread_id"] == "t-42"
    assert formatted["timestamp"]


def test_system_log_event_without_thread_maps_none():
    event = SystemLogEvent(log_type="macro_thought", log_data={"text": "x"})

    assert format_event_for_frontend(event)["thread_id"] is None
