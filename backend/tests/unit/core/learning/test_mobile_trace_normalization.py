"""Mobile mirror trace normalization + macro compilation regression tests.

The Android mirror recorder persists raw events (touch_down/touch_up/swipe/key)
with source="mobile". TraceParser keeps these events raw; MacroScriptCompiler
normalizes them into macro-executable actions. These tests pin the contract:
- touch boundaries are dropped (the composed swipe/tap event covers them)
- swipe with real travel -> swipe action with end coords
- near-zero swipe -> tap
- key -> key_press
- compiled macro steps carry source=mobile so the voice/REST gate and the
  mobile executor accept them
"""

import pytest

from app.core.execution.macro.compiler import MacroScriptCompiler
from app.core.execution.macro.schemas import MacroSource
from app.core.learning.workflow_synthesizer import WorkflowSynthesizer
from app.core.learning.trace_parser import TraceParser
from app.models.learning import TraceEvent


def _mobile_event(event_type: str, payload: dict, step: int = 1, **kw) -> TraceEvent:
    return TraceEvent(
        member_id=0,
        thread_id="t-mobile",
        session_id="s-mobile",
        recording_session_id="s-mobile",
        step_number=step,
        node_name=kw.pop("node_name", "device-1"),
        event_type=event_type,
        payload=payload,
        source="mobile",
        app_name=kw.pop("app_name", "com.example.app"),
        is_human_action=True,
        state_snapshot={"context": "android_mirror"},
        **kw,
    )


def _sequence(*events: TraceEvent):
    return TraceParser("t-mobile", "s-mobile")._convert_to_sequence(list(events))


class TestMobileEventPreservation:
    """TraceParser no longer normalizes mobile events; it keeps them raw."""

    def test_touch_boundaries_preserved_as_raw(self):
        seq = _sequence(
            _mobile_event("touch_down", {"x": 100, "y": 200}, step=1),
            _mobile_event("touch_up", {"x": 100, "y": 200}, step=2),
        )
        assert len(seq.steps) == 2
        assert seq.steps[0].action_type == "touch_down"
        assert seq.steps[1].action_type == "touch_up"

    def test_swipe_preserved_as_raw(self):
        seq = _sequence(
            _mobile_event(
                "swipe",
                {
                    "x": 100,
                    "y": 800,
                    "swipe_end_x": 100,
                    "swipe_end_y": 200,
                    "swipe_duration_ms": 350,
                },
            )
        )
        assert len(seq.steps) == 1
        step = seq.steps[0]
        assert step.action_type == "swipe"

    def test_key_event_preserved_as_raw(self):
        seq = _sequence(_mobile_event("key", {"key_code": 4}))
        assert seq.steps[0].action_type == "key"

    def test_state_context_carries_app_and_source(self):
        seq = _sequence(_mobile_event("swipe", {"x": 1, "y": 2}))
        ctx = seq.steps[0].state_context
        assert ctx["app_name"] == "com.example.app"
        assert ctx["source"] == "mobile"


class TestMobileMacroCompilation:
    def test_touch_boundaries_dropped_by_compiler(self):
        seq = _sequence(
            _mobile_event("touch_down", {"x": 100, "y": 200}, step=1),
            _mobile_event("touch_up", {"x": 100, "y": 200}, step=2),
        )
        script = MacroScriptCompiler().compile(seq)
        assert script.steps == []

    def test_real_swipe_becomes_swipe_action(self):
        seq = _sequence(
            _mobile_event(
                "swipe",
                {
                    "x": 100,
                    "y": 800,
                    "swipe_end_x": 100,
                    "swipe_end_y": 200,
                    "swipe_duration_ms": 350,
                },
            )
        )
        script = MacroScriptCompiler().compile(seq)
        assert len(script.steps) == 1
        step = script.steps[0]
        assert step.event_type == "swipe"
        assert step.payload["end_x"] == 100
        assert step.payload["end_y"] == 200
        assert step.payload["duration_ms"] == 350

    def test_zero_distance_swipe_becomes_tap(self):
        seq = _sequence(
            _mobile_event(
                "swipe", {"x": 540, "y": 1200, "swipe_end_x": 542, "swipe_end_y": 1198}
            )
        )
        script = MacroScriptCompiler().compile(seq)
        assert len(script.steps) == 1
        step = script.steps[0]
        assert step.event_type == "tap"
        assert step.payload["x"] == 540
        assert step.payload["y"] == 1200
        assert "end_x" not in step.payload

    def test_swipe_without_end_coords_becomes_tap(self):
        seq = _sequence(_mobile_event("swipe", {"x": 10, "y": 20}))
        script = MacroScriptCompiler().compile(seq)
        assert script.steps[0].event_type == "tap"

    def test_key_event_becomes_key_press(self):
        seq = _sequence(_mobile_event("key", {"key_code": 4}))
        script = MacroScriptCompiler().compile(seq)
        assert script.steps[0].event_type == "key_press"
        assert script.steps[0].payload["key"] == 4

    def test_compiled_steps_carry_mobile_source(self):
        seq = _sequence(
            _mobile_event(
                "swipe",
                {"x": 540, "y": 1200, "swipe_end_x": 540, "swipe_end_y": 1199},
                step=1,
            ),
            _mobile_event(
                "swipe",
                {"x": 100, "y": 900, "swipe_end_x": 100, "swipe_end_y": 300},
                step=2,
            ),
        )
        script = MacroScriptCompiler().compile(seq)

        assert len(script.steps) == 2
        sources = {s.source for s in script.steps}
        assert sources == {MacroSource.MOBILE}
        event_types = [s.event_type for s in script.steps]
        assert event_types == ["tap", "swipe"]
        swipe_step = script.steps[1]
        assert swipe_step.payload["end_x"] == 100
        assert swipe_step.payload["end_y"] == 300


class TestMultimodalCompileFromEvents:
    """Regression: _compile_macro_from_events used to isinstance-check a
    MacroScript object against str/list and always returned []."""

    @pytest.mark.asyncio
    async def test_returns_compiled_steps(self):
        from app.core.learning.multimodal_synthesizer import MultimodalSkillSynthesizer

        events = [
            _mobile_event(
                "swipe",
                {"x": 540, "y": 1200, "swipe_end_x": 540, "swipe_end_y": 1199},
                step=1,
            ),
        ]
        synth = MultimodalSkillSynthesizer.__new__(MultimodalSkillSynthesizer)
        steps = await synth._compile_macro_from_events(events)

        assert isinstance(steps, list)
        assert len(steps) == 1
        assert steps[0]["event_type"] == "tap"
        assert steps[0]["source"] == "mobile"


class TestSkillYamlParsing:
    """Regression: unparsable LLM YAML used to persist a sentinel skill named
    'unparsed_skill' that looked successful."""

    def test_garbage_yaml_raises(self):
        synth = WorkflowSynthesizer(thread_id="t")
        with pytest.raises(ValueError):
            synth._parse_yaml("name: [unclosed\n  bad: : :", None)

    def test_non_mapping_yaml_raises(self):
        synth = WorkflowSynthesizer(thread_id="t")
        with pytest.raises(ValueError):
            synth._parse_yaml("- just\n- a\n- list", None)

    def test_dict_macro_script_ignored(self):
        from app.core.learning.trace_parser import TraceSequence

        synth = WorkflowSynthesizer(thread_id="t")
        yaml_str = """
name: demo
description: d
macro_script:
  version: "1.0"
  steps:
    - type: action
      event_type: tap
      source: mobile
      payload: {x: 1, y: 2}
"""
        skill = synth._parse_yaml(yaml_str, TraceSequence(thread_id="t"))
        assert skill.name == "demo"
        assert skill.instructions is None

    def test_mirror_window_click_becomes_tap_with_device_pixels(self):
        """Mirror-window recording path: GlobalRecorderManager transforms
        screen coords to device pixels client-side and tags source=mobile."""
        seq = _sequence(
            _mobile_event("mouse_click", {"position": [540, 1200], "platform": "macos"})
        )
        assert len(seq.steps) == 1
        step = seq.steps[0]
        assert step.action_type == "mouse_click"

    def test_mirror_window_click_compiles_to_mobile_macro(self):
        seq = _sequence(
            _mobile_event("mouse_click", {"position": [540, 1200]}, step=1),
        )
        script = MacroScriptCompiler().compile(seq)
        assert len(script.steps) == 1
        assert script.steps[0].source == MacroSource.MOBILE
        assert script.steps[0].event_type == "tap"
        assert script.steps[0].payload["x"] == 540


class TestCompilerEnumMapping:
    """Regression: MacroScriptCompiler must only emit MacroActionType-valid
    event types (enum-validated MacroStep), including legacy trace names."""

    def test_tool_call_navigate_and_input_text_remap(self):
        seq = _sequence(
            TraceEvent(
                member_id=0,
                thread_id="t-mobile",
                step_number=1,
                node_name="worker",
                event_type="tool_call",
                payload={
                    "name": "browser_control",
                    "args": {"action": "navigate", "url": "https://x.example"},
                },
                source="agent",
            ),
            _mobile_event("input_text", {"text": "hello"}, step=2),
        )
        script = MacroScriptCompiler().compile(seq)
        types = [s.event_type for s in script.steps]
        assert "navigate" in types  # goto remapped back to the enum member
        assert "goto" not in types
        assert "input" in types  # input_text remapped to the enum member
        assert "input_text" not in types

    def test_mobile_app_transition_emits_open_app_not_launch_app(self):
        seq = _sequence(
            _mobile_event("tap", {"x": 1, "y": 2}, step=1, app_name="com.a.app"),
            _mobile_event("tap", {"x": 3, "y": 4}, step=2, app_name="com.b.app"),
        )
        # Must not raise (LAUNCH_APP is not a MacroActionType member)
        script = MacroScriptCompiler().compile(seq)
        assert any(s.event_type == "open_app" for s in script.steps)
