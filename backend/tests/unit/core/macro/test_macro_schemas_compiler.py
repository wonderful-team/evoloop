"""Tests for macro schemas (YAML round-trip) and the compiler's action
normalization (tool_call / mobile mirror events)."""

from app.core.learning.macro.compiler import MacroScriptCompiler
from app.core.learning.macro.schemas import (
    MacroScript,
    MacroSource,
    MacroStep,
    MacroStepType,
)


class TestMacroScriptYaml:
    def test_to_yaml_from_yaml_roundtrip(self):
        script = MacroScript(
            steps=[
                MacroStep(
                    type=MacroStepType.ACTION,
                    event_type="click",
                    source=MacroSource.DOM,
                    target_selector="#btn",
                    payload={"button": "left"},
                )
            ]
        )
        yaml_str = script.to_yaml()
        assert "steps:" in yaml_str

        parsed = MacroScript.from_yaml(yaml_str)
        assert len(parsed.steps) == 1
        assert parsed.steps[0].type == MacroStepType.ACTION
        assert parsed.steps[0].event_type == "click"

    def test_payload_stays_plain_dict(self):
        step = MacroStep(
            type=MacroStepType.ACTION,
            event_type="navigate",
            source=MacroSource.DOM,
            payload={"url": "https://x.com"},
        )
        assert isinstance(step.payload, dict)
        assert step.payload == {"url": "https://x.com"}


class TestCompilerNormalization:
    def _compile(self, step):
        from app.core.learning.schemas.migrated import (
            ActionCategory,
            ActionSource,
            TraceStep,
        )
        from app.core.learning.trace.parser import TraceSequence

        trace = TraceSequence(
            thread_id="t",
            steps=[TraceStep(step_number=1, source=ActionSource.AGENT, category=ActionCategory.INTERACTION, **step)],
        )
        return MacroScriptCompiler().compile(trace)

    def test_tool_call_navigate_normalized(self):
        script = self._compile(
            {"action_type": "tool_call", "action_name": "navigate", "action_args": {"action": "navigate", "url": "https://x.com"}}
        )
        assert len(script.steps) == 1
        assert script.steps[0].type == MacroStepType.ACTION

    def test_tool_call_type_text_normalized_to_input(self):
        script = self._compile(
            {"action_type": "tool_call", "action_name": "type_text", "action_args": {"action": "type_text", "text": "hi"}}
        )
        assert len(script.steps) >= 1

    def test_mobile_mouse_click_to_tap(self):
        script = self._compile(
            {
                "action_type": "mouse_click",
                "action_name": "mouse_click",
                "action_args": {"position": [100, 200]},
                "state_context": {"source": "mobile"},
            }
        )
        assert len(script.steps) == 1
        assert script.steps[0].type == MacroStepType.ACTION

    def test_mobile_swipe(self):
        script = self._compile(
            {
                "action_type": "swipe",
                "action_name": "swipe",
                "action_args": {"x": 100, "y": 200, "swipe_end_x": 300, "swipe_end_y": 400},
                "state_context": {"source": "mobile"},
            }
        )
        assert len(script.steps) == 1
        assert script.steps[0].type == MacroStepType.ACTION
