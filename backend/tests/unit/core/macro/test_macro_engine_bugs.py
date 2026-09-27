"""Regression tests for macro engine audit findings (P1 engine bugs).

Each test reproduces a defect found in the engine audit. They must pass after
the fix and fail (red) on the pre-fix code.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.learning.macro.schemas import MacroSource, MacroStep, MacroStepType


# ---------------------------------------------------------------------------
# _loops.py:230 — collect-mode DETAIL phase crashes on int(None) when
# detail_config has no "limit" key (audit P1)
# ---------------------------------------------------------------------------
class TestCollectDetailMissingLimit:
    @pytest.mark.asyncio
    async def test_detail_phase_without_limit_does_not_crash(self, tmp_path):
        from app.core.learning.macro.engine import LoopMixin

        state_file = tmp_path / "collect_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "items": [
                        {"signature": "sig_1", "status": "pending", "tap_x": 1, "tap_y": 2}
                    ],
                    "phase": "detail",
                }
            ),
            encoding="utf-8",
        )

        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.MOBILE,
            description="collect detail",
            steps=[],
        )

        with patch(
            "app.core.environment.controllers.mobile.MobileController.execute",
            new=AsyncMock(return_value="OK"),
        ), patch(
            "app.core.learning.macro.engine.loops.activity_monitor.log_event",
            new=AsyncMock(),
        ):
            ok, msg, _ = await LoopMixin._handle_collect_loop(
                thread_id="test",
                step=step,
                payload={"state_file": str(state_file)},
                params={},
                extracted_data={},
                disable_ocr=True,
                collect_mode="detail",
            )
        assert ok is True


# ---------------------------------------------------------------------------
# compiler.py:223 — a trace step with action_type="extract" passes the
# ALLOWED_UI_ACTIONS whitelist but is not a MacroActionType member, so
# MacroActionType(event_type) raises ValueError (audit P1)
# ---------------------------------------------------------------------------
class TestCompilerExtractAction:
    def test_compile_extract_action_does_not_crash(self):
        from app.core.learning.macro.compiler import MacroScriptCompiler
        from app.core.learning.schemas.migrated import (
            ActionCategory,
            ActionSource,
            TraceStep,
        )
        from app.core.learning.trace.parser import TraceSequence

        trace = TraceSequence(
            thread_id="t",
            steps=[
                TraceStep(
                    step_number=1,
                    source=ActionSource.AGENT,
                    category=ActionCategory.INTERACTION,
                    action_type="extract",
                    action_name="extract",
                    node_name="browser_interaction",
                )
            ],
        )
        script = MacroScriptCompiler().compile(trace)
        assert script is not None
        assert len(script.steps) >= 1


# ---------------------------------------------------------------------------
# _native.py — a native script with a non-zero returncode is silently
# reported as success (audit P1)
# ---------------------------------------------------------------------------
class TestNativeNonZeroReturnCode:
    @pytest.mark.asyncio
    async def test_nonzero_returncode_is_failure(self):
        from app.core.learning.macro.engine import NativeMixin

        fake_process = AsyncMock()
        fake_process.returncode = 1
        fake_process.communicate = AsyncMock(
            return_value=(b"", b"boom")
        )

        with patch(
            "app.core.atlas.script_gate.check_native_allowed",
            return_value=True,
        ), patch(
            "app.core.learning.macro.engine.native.asyncio.create_subprocess_exec",
            return_value=fake_process,
        ), patch(
            "app.core.learning.macro.engine.native.activity_monitor.log_event",
            new=AsyncMock(),
        ):
            with pytest.raises(ValueError):
                await NativeMixin._handle_native(
                    thread_id="test",
                    payload={"script_path": "/tmp/script.py", "command": "python3"},
                    extracted_data={},
                )


# ---------------------------------------------------------------------------
# _control.py — a LOOP step without a condition iterates zero times because
# _evaluate_condition(None, ...) returns None (audit P2)
# ---------------------------------------------------------------------------
class TestLoopWithoutCondition:
    @pytest.mark.asyncio
    async def test_loop_without_condition_runs_up_to_max_iterations(self):
        from app.core.learning.macro.engine import ControlMixin

        calls: list[int] = []

        class _LoopCtrl(ControlMixin):
            @classmethod
            async def execute_steps(cls, *args, **kwargs):
                calls.append(1)
                return True, "", None

        inner = MacroStep(type=MacroStepType.ACTION, source=MacroSource.DOM, steps=[])
        step = MacroStep(
            type=MacroStepType.LOOP,
            source=MacroSource.DOM,
            steps=[inner],
            max_iterations=5,
        )

        ok, msg, _ = await _LoopCtrl._handle_control_flow(
            thread_id="test",
            step=step,
            payload={},
            params={},
            extracted_data={},
        )
        assert ok is True
        assert len(calls) == 5  # unconditional LOOP runs up to max_iterations


# ---------------------------------------------------------------------------
# schemas.py — payload union default values silently override the engine's
# own timeout default (audit P2): MacroPayload model_dump() injects
# NavigationPayload.timeout_ms=30000 etc into every payload
# ---------------------------------------------------------------------------
class TestPayloadDefaults:
    def test_payload_model_dump_does_not_impose_union_defaults(self):
        from app.core.learning.macro.schemas import MacroStep

        step = MacroStep(
            type=MacroStepType.ACTION,
            event_type="click",
            source=MacroSource.DOM,
            payload={"x": 1, "y": 2},
        )
        # Payload is a plain dict now; the engine owns its own timeout default
        # and the payload must not be silently stamped with model defaults.
        assert isinstance(step.payload, dict)
        assert "timeout_ms" not in step.payload
