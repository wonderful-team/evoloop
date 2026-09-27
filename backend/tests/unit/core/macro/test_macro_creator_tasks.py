"""Tests for MacroCreatorService replayability filtering."""


from app.core.learning.macro.creator import MacroCreatorService
from app.models.learning import TraceEvent


def _trace_event(**kwargs) -> TraceEvent:
    defaults = {
        "thread_id": "t",
        "step_number": 1,
        "node_name": "browser_interaction",
        "event_type": "click",
        "payload": {},
    }
    defaults.update(kwargs)
    return TraceEvent(**defaults)


class TestIsReplayable:
    def test_message_id_not_seen_returns_false(self):
        ev = _trace_event(message_id="m1")
        assert MacroCreatorService._is_replayable(ev, {"m2", "m3"}) is False

    def test_excluded_event_type_returns_false(self):
        ev = _trace_event(event_type="llm_output")
        assert MacroCreatorService._is_replayable(ev, set()) is False

    def test_negative_reward_returns_false(self):
        ev = _trace_event(reward=-1.0)
        assert MacroCreatorService._is_replayable(ev, set()) is False

    def test_failed_payload_returns_false(self):
        ev = _trace_event(payload={"success": False})
        assert MacroCreatorService._is_replayable(ev, set()) is False

    def test_replayable_event_type_returns_true(self):
        ev = _trace_event(event_type="click")
        assert MacroCreatorService._is_replayable(ev, set()) is True

    def test_tool_call_wrapping_replayable_action(self):
        ev = _trace_event(event_type="tool_call", payload={"args": {"action": "click"}})
        assert MacroCreatorService._is_replayable(ev, set()) is True

    def test_unrelated_event_returns_false(self):
        ev = _trace_event(event_type="unknown_event")
        assert MacroCreatorService._is_replayable(ev, set()) is False
