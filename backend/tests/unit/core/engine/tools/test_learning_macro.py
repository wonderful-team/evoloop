"""Unit tests for macro family/risk helpers and parameter finalization."""

from __future__ import annotations

from app.core.learning.macro.schemas import (
    DEFAULT_ALLOWED_FAMILIES,
    MacroStep,
    compute_max_risk,
    scan_step_families,
)
from app.utils.parameters import finalize_macro_parameters


class TestScanStepFamilies:
    def test_allows_observe_act_control_data(self):
        steps = [
            MacroStep(type="action", event_type="wait", payload={"seconds": 1}, step_number=1),
            MacroStep(type="action", event_type="click", payload={}, step_number=2),
            MacroStep(type="control", payload={}, step_number=3),
        ]
        assert scan_step_families(steps, {"observe", "act", "control", "data"}) is None

    def test_rejects_bash(self):
        steps = [
            MacroStep(
                type="bash",
                event_type="bash",
                payload={"command": "echo hi", "key": "out"},
                step_number=1,
            ),
        ]
        reason = scan_step_families(steps, {"observe", "act", "control", "data"})
        assert reason is not None
        assert "bash" in reason

    def test_rejects_native_applescript(self):
        steps = [
            MacroStep(
                type="native",
                event_type="applescript",
                payload={"script": 'tell app "Finder" to activate'},
                step_number=1,
            ),
        ]
        reason = scan_step_families(steps, {"observe", "act", "control", "data"})
        assert reason is not None
        assert "escape" in reason or "native" in reason

    def test_rejects_run_js(self):
        steps = [
            MacroStep(
                type="action",
                event_type="run_js",
                payload={"js": "document.title"},
                step_number=1,
            ),
        ]
        reason = scan_step_families(steps, {"observe", "act", "control", "data"})
        assert reason is not None
        assert "run_js" in reason

    def test_rejects_nested_escape_in_if(self):
        steps = [
            MacroStep(
                type="if",
                payload={},
                step_number=1,
                then_steps=[
                    MacroStep(
                        type="bash",
                        event_type="bash",
                        payload={"command": "rm -rf /", "key": "out"},
                        step_number=2,
                    ),
                ],
            ),
        ]
        reason = scan_step_families(steps, {"observe", "act", "control", "data"})
        assert reason is not None
        assert "bash" in reason


class TestComputeMaxRisk:
    def test_observe_only(self):
        steps = [
            MacroStep(type="action", event_type="wait", payload={"seconds": 1}, step_number=1),
        ]
        assert compute_max_risk(steps) == "observe"

    def test_act_higher_than_observe(self):
        steps = [
            MacroStep(type="action", event_type="wait", payload={}, step_number=1),
            MacroStep(type="action", event_type="click", payload={}, step_number=2),
        ]
        assert compute_max_risk(steps) == "act"

    def test_data_input(self):
        steps = [
            MacroStep(type="action", event_type="input", payload={"text": "x"}, step_number=1),
        ]
        assert compute_max_risk(steps) == "data"

    def test_escape_bash(self):
        steps = [
            MacroStep(
                type="bash",
                event_type="bash",
                payload={"command": "echo hi", "key": "out"},
                step_number=1,
            ),
        ]
        assert compute_max_risk(steps) == "escape"

    def test_nested_max_risk(self):
        steps = [
            MacroStep(
                type="if",
                payload={},
                step_number=1,
                then_steps=[
                    MacroStep(
                        type="bash",
                        event_type="bash",
                        payload={"command": "echo hi", "key": "out"},
                        step_number=2,
                    ),
                ],
            ),
        ]
        assert compute_max_risk(steps) == "escape"


class TestFinalizeMacroParameters:
    def test_declared_parameters_win(self):
        declared = [{"name": "stock_threshold", "type": "string", "required": True}]
        result = finalize_macro_parameters(declared, "{{base_url}}/x {{stock_threshold}}")
        assert [p["name"] for p in result] == ["stock_threshold"]
        assert result[0]["type"] == "string"
        assert result[0]["required"] is True

    def test_derived_from_placeholders_excludes_base_url(self):
        yaml = "url: {{base_url}}/shop.html\nthreshold: {{stock_threshold}}\n"
        result = finalize_macro_parameters(None, yaml)
        names = [p["name"] for p in result]
        assert names == ["stock_threshold"]
        assert "base_url" not in names
        assert result[0]["required"] is True

    def test_empty_when_no_placeholders(self):
        assert finalize_macro_parameters(None, "version: '1.0'\nsteps: []") == []

    def test_normalizes_mixed_input(self):
        result = finalize_macro_parameters(
            [{"name": "kw", "type": "string", "required": False}],
            "{{kw}} {{ignored}}",
        )
        assert result[0]["required"] is False


class TestMacroStepTreeWalk:
    """Shared scan_step_families / compute_max_risk must accept MacroStep
    objects AND plain dicts identically (learning.py uses objects,
    update_macro.py uses dicts)."""

    def _object_steps(self):
        return [
            MacroStep(type="action", event_type="wait", payload={"seconds": 1}, step_number=1),
            MacroStep(
                type="extract", event_type="run_js", extract_type="run_js",
                payload={"script": "() => 1"}, step_number=2,
            ),
        ]

    def _dict_steps(self):
        return [
            {"type": "action", "event_type": "wait", "payload": {"seconds": 1}, "step_number": 1},
            {"type": "extract", "event_type": "run_js", "extract_type": "run_js",
             "payload": {"script": "() => 1"}, "step_number": 2},
        ]

    def test_object_and_dict_scan_agree(self):
        allowed = {"observe", "act", "control", "data"}
        assert scan_step_families(self._object_steps(), allowed) is None
        assert scan_step_families(self._dict_steps(), allowed) is None

    def test_object_and_dict_risk_agree(self):
        assert compute_max_risk(self._object_steps()) == compute_max_risk(self._dict_steps()) == "data"

    def test_run_js_in_extract_is_data_not_escape(self):
        # run_js used to READ page state in an EXTRACT step is observation.
        steps = [MacroStep(type="extract", event_type="run_js", extract_type="run_js",
                           payload={"script": "() => 1"}, step_number=1)]
        assert compute_max_risk(steps) == "data"
        assert scan_step_families(steps, {"observe", "act", "control", "data"}) is None

    def test_run_js_as_action_is_escape(self):
        steps = [MacroStep(type="action", event_type="run_js", payload={"script": "() => 1"}, step_number=1)]
        assert compute_max_risk(steps) == "escape"
        assert scan_step_families(steps, {"observe", "act", "control", "data"}) is not None

    def test_recursive_nested_risk(self):
        steps = [
            MacroStep(
                type="if", payload={}, step_number=1,
                then_steps=[MacroStep(type="bash", event_type="bash",
                                      payload={"command": "rm -rf /", "key": "o"}, step_number=2)],
            )
        ]
        assert compute_max_risk(steps) == "escape"
        assert scan_step_families(steps, {"observe", "act", "control", "data"}) is not None

    def test_dict_recursive_rejection(self):
        steps = [
            {"type": "loop", "payload": {}, "step_number": 1,
             "steps": [{"type": "native", "event_type": "applescript",
                        "payload": {"script": "x"}, "step_number": 2}]}
        ]
        assert scan_step_families(steps, {"observe", "act", "control", "data"}) is not None


class TestDefaultAllowedFamilies:
    """DEFAULT_ALLOWED_FAMILIES is the single source of truth for the
    Agent-authored macro gate shared by create_macro (learning.py) and the
    update_macro rewrite path. Its value must match the allowed set used by
    scan_step_families/compute_max_risk in those two consumers, so the risk
    gate cannot silently drift between them."""

    def test_constant_value(self):
        # 临时放开 escape，允许宏内使用 bash 等数据加工步骤
        assert DEFAULT_ALLOWED_FAMILIES == frozenset(
            {"observe", "act", "control", "data", "escape"}
        )

    def test_constant_accepts_safe_script(self):
        steps = [
            MacroStep(
                type="extract",
                event_type="run_js",
                extract_type="run_js",
                payload={"script": "() => 1"},
                step_number=1,
            ),
            MacroStep(type="action", event_type="click", payload={}, step_number=2),
            MacroStep(type="control", payload={}, step_number=3),
        ]
        assert scan_step_families(steps, DEFAULT_ALLOWED_FAMILIES) is None
        assert compute_max_risk(steps) in DEFAULT_ALLOWED_FAMILIES

    def test_constant_allows_escape_family(self):
        # escape 族已临时放开，bash 步骤应被允许
        steps = [MacroStep(type="bash", event_type="bash",
                           payload={"command": "echo hi", "key": "o"}, step_number=1)]
        assert scan_step_families(steps, DEFAULT_ALLOWED_FAMILIES) is None

    def test_authoring_is_single_gate(self):
        import inspect

        from app.core.learning.macro import authoring

        src = inspect.getsource(authoring)
        assert "DEFAULT_ALLOWED_FAMILIES" in src
        assert "verify_macro_script" in src

