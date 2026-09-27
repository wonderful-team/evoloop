"""Tests for macro utils — step normalization (cleanup_macro_steps) and
dry-run verification (verify_macro_script)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.learning.macro.utils import cleanup_macro_steps


class TestCleanupMacroSteps:
    def test_wait_normalized_to_action(self):
        steps, _ = cleanup_macro_steps(
            [{"type": "wait", "timeout": 1500, "step_number": 1}]
        )
        step = steps[0]
        assert step["type"] == "action"
        assert step["event_type"] == "wait"
        assert step["payload"]["seconds"] == 1.5

    def test_loop_types_normalized(self):
        steps, _ = cleanup_macro_steps(
            [
                {"type": "while", "steps": [], "step_number": 1},
                {"type": "batch_loop", "steps": [], "step_number": 2},
            ]
        )
        assert steps[0]["type"] == "loop"
        assert steps[1]["type"] == "loop"

    def test_then_else_renamed(self):
        steps, _ = cleanup_macro_steps(
            [
                {
                    "type": "if",
                    "then": [{"type": "action", "step_number": 2}],
                    "else": [{"type": "action", "step_number": 3}],
                    "step_number": 1,
                }
            ]
        )
        step = steps[0]
        assert "then" not in step and "else" not in step
        assert len(step["then_steps"]) == 1
        assert len(step["else_steps"]) == 1

    def test_do_renamed_to_steps(self):
        steps, _ = cleanup_macro_steps(
            [{"type": "loop", "do": [{"type": "action", "step_number": 1}], "step_number": 1}]
        )
        step = steps[0]
        assert "do" not in step
        assert len(step["steps"]) == 1

    def test_nested_step_numbers_unique(self):
        steps, _ = cleanup_macro_steps(
            [
                {
                    "type": "if",
                    "then_steps": [{"type": "action"}],
                    "else_steps": [{"type": "action"}],
                    "step_number": 1,
                },
                {"type": "action", "step_number": 2},
            ]
        )
        # nested numbers are assigned in DFS order from the shared counter
        assert steps[0]["then_steps"][0]["step_number"] == 2
        assert steps[0]["else_steps"][0]["step_number"] == 3
        assert steps[1]["step_number"] == 4


class TestVerifyMacroScript:
    @pytest.mark.asyncio
    async def test_verify_success(self):
        from app.core.learning.macro.utils import verify_macro_script

        with patch(
            "app.core.learning.macro.utils.MacroService.run",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "extracted_data": {"title": "x"},
                    "message": "ok",
                }
            ),
        ):
            result = await verify_macro_script(
                [{"type": "extract", "key": "title"}], thread_id="t"
            )
        assert result.status == "success"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_verify_missing_extract_key(self):
        from app.core.learning.macro.utils import verify_macro_script

        with patch(
            "app.core.learning.macro.utils.MacroService.run",
            new=AsyncMock(
                return_value={"success": True, "extracted_data": {}, "message": "ok"}
            ),
        ):
            result = await verify_macro_script(
                [{"type": "extract", "key": "title"}], thread_id="t"
            )
        assert result.status == "failed"
        assert "title" in result.missing_keys

    @pytest.mark.asyncio
    async def test_verify_success_extracts_all_keys(self):
        from app.core.learning.macro.utils import verify_macro_script

        with patch(
            "app.core.learning.macro.utils.MacroService.run",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "extracted_data": {"title": "x", "price": "10"},
                    "message": "ok",
                }
            ),
        ):
            result = await verify_macro_script(
                [
                    {"type": "extract", "key": "title"},
                    {"type": "extract", "key": "price"},
                ],
                thread_id="t",
            )
        assert result.status == "success"
        assert result.success is True
        assert result.extracted_count == 2
