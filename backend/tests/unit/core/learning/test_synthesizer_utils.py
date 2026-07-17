"""Regression tests for synthesizer_utils guards."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.execution.macro.utils import verify_macro_script


@pytest.mark.asyncio
async def test_verify_macro_script_handles_none_extracted_data():
    """B7 regression: MacroService.run returns extracted_data=None on failure
    paths; the verifier must not crash on `.keys()`/membership checks."""
    fake_result = {
        "success": False,
        "extracted_data": None,
        "error": "device disconnected",
    }
    with patch(
        "app.core.execution.macro.service.MacroService.run",
        new_callable=AsyncMock,
        return_value=fake_result,
    ):
        result = await verify_macro_script(
            macro_script=[{"type": "extract", "key": "price"}],
            thread_id="t-b7",
        )

    assert result.status == "failed"
    assert result.missing_keys == ["price"]
    assert result.extracted_count == 0
    assert result.error == "device disconnected"


@pytest.mark.asyncio
async def test_verify_macro_script_parses_yaml_string_before_run():
    """Regression: a YAML string macro must be parsed to a step list before
    MacroService.run — passing the raw string crashed with
    'str' object has no attribute 'steps' (escaped the route's narrow except
    as a bare 500 and rolled back the freshly synthesized skill row)."""
    yaml_macro = "- type: action\n  event_type: click\n  step_number: 1\n"
    captured = {}

    async def fake_run(*, thread_id, script_input, params):  # noqa: ARG001
        captured["script_input"] = script_input
        return {"success": True, "extracted_data": {}, "error": None}

    with patch(
        "app.core.execution.macro.service.MacroService.run",
        new_callable=AsyncMock,
        side_effect=fake_run,
    ):
        result = await verify_macro_script(macro_script=yaml_macro, thread_id="t-yaml")

    assert isinstance(captured["script_input"], list)
    assert captured["script_input"][0]["event_type"] == "click"
    assert result.status == "success"
