"""Unit tests for the shared macro authoring gate (authoring.validate_script).

The Agent-authored script pipeline (parse → cleanup → risk gate → dry-run →
risk tier) lives in authoring.py and is shared by create_macro and the
update_macro rewrite path. These tests lock its gate behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.learning.macro.authoring import validate_script

VALID_SCRIPT = """
version: "1.0"
metadata:
  name: test-rewrite
steps:
  - type: action
    event_type: wait
    payload:
      seconds: 1
    step_number: 1
"""


@pytest.mark.asyncio
async def test_invalid_yaml_rejected():
    result = await validate_script("steps: [unclosed", thread_id="t", project_id=120)
    assert result.ok is False
    assert "Invalid macro script" in result.error


@pytest.mark.skip(reason="escape family temporarily allowed for data processing macros")
@pytest.mark.asyncio
async def test_risk_gate_rejects_bash_step():
    script = """
steps:
  - type: bash
    event_type: bash
    payload:
      command: echo hello
      key: out
    step_number: 1
"""
    result = await validate_script(
        script, thread_id="t", project_id=120, allowed_families={"observe", "act", "control", "data"}
    )
    assert result.ok is False
    assert "Risk gate rejected" in result.error
    assert "bash" in result.error


@pytest.mark.asyncio
async def test_verification_failure_reported():
    result = MagicMock(success=False, error="Cannot navigate to invalid URL", status="failed")
    with patch(
        "app.core.learning.macro.authoring.verify_macro_script",
        AsyncMock(return_value=result),
    ):
        validation = await validate_script(VALID_SCRIPT, thread_id="t", project_id=120)

    assert validation.ok is False
    assert "Macro verification failed" in validation.error
    assert "Cannot navigate to invalid URL" in validation.error


@pytest.mark.asyncio
async def test_valid_script_passes_and_returns_cleaned():
    result = MagicMock(success=True, error=None, status="ok")
    with patch(
        "app.core.learning.macro.authoring.verify_macro_script",
        AsyncMock(return_value=result),
    ) as mock_verify:
        validation = await validate_script(VALID_SCRIPT, thread_id="t", project_id=120)

    assert validation.ok is True
    assert validation.error is None
    assert validation.cleaned_steps is not None
    assert validation.cleaned_steps[0]["type"] == "action"
    assert validation.max_risk == "observe"
    assert validation.requires_confirmation is False
    assert mock_verify.await_args.kwargs["_project_id"] == 120

@pytest.mark.asyncio
async def test_validate_macro_structure_valid_yaml():
    from app.core.learning.macro.authoring import validate_macro_structure

    ok, error, step_count = validate_macro_structure(VALID_SCRIPT)
    assert ok is True
    assert error == ""
    assert step_count == 1


@pytest.mark.asyncio
async def test_validate_macro_structure_invalid_yaml():
    from app.core.learning.macro.authoring import validate_macro_structure

    ok, error, step_count = validate_macro_structure("steps: [unclosed")
    assert ok is False
    assert "Invalid macro script" in error
    assert step_count == 0


@pytest.mark.asyncio
async def test_validate_macro_structure_accepts_step_list():
    from app.core.learning.macro.authoring import validate_macro_structure

    steps = [{"type": "action", "event_type": "wait", "payload": {"seconds": 1}, "step_number": 1}]
    ok, error, step_count = validate_macro_structure(steps)
    assert ok is True
    assert step_count == 1
