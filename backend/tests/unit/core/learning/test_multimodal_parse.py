"""Regression tests for multimodal synthesis parse + verification contracts."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.execution.macro.utils import verify_macro_script
from app.core.learning.multimodal_synthesizer import (
    MultimodalSkillSynthesizer,
    RecordingSession,
)


def _recording() -> RecordingSession:
    return RecordingSession(
        session_id="s1",
        thread_id="t1",
        video_path="/tmp/v.mp4",
        task_description="do things",
    )


def _synthesizer() -> MultimodalSkillSynthesizer:
    """Bypass __init__ (Vision LLM factory needs runtime config); the parse
    helpers under test are pure."""
    return MultimodalSkillSynthesizer.__new__(MultimodalSkillSynthesizer)


class TestParseLlmResponseMacroContract:
    def test_dict_macro_script_becomes_step_list(self):
        """The prompt asks for macro_script as a YAML object; a spec-compliant
        LLM response must not crash the str-typed field (pre-B1)."""
        response = """```yaml
name: demo_skill
description: demo
macro_script:
  version: "1.0"
  steps:
    - step_number: 1
      type: action
      event_type: tap
```
# Expert Skill Guide
do the thing
"""
        result = _synthesizer()._parse_llm_response(response, _recording())
        assert isinstance(result, dict)
        assert isinstance(result["macro_script"], list)
        assert result["macro_script"][0]["event_type"] == "tap"
        assert result["skill"].name == "demo_skill"

    def test_missing_macro_script_is_none(self):
        response = """```yaml
name: demo_skill
description: demo
```
plain text instructions
"""
        result = _synthesizer()._parse_llm_response(response, _recording())
        assert isinstance(result, dict)
        assert result["macro_script"] is None
        assert result["skill"].name == "demo_skill"


class TestVerifyMacroYamlString:
    @pytest.mark.asyncio
    async def test_yaml_string_is_parsed_before_verification(self):
        """verify_macro_script consumes a step list; passing a raw YAML string
        iterated char-by-char and always failed (pre-B5), forcing every
        skill to agentic mode."""
        captured = {}

        async def fake_run(*, thread_id, script_input, params):  # noqa: ARG001
            captured["script_input"] = script_input
            return {"success": True, "extracted_data": {}, "error": None}

        yaml_str = "- step_number: 1\n  type: action\n  event_type: tap\n"
        with patch(
            "app.core.execution.macro.service.MacroService.run",
            new_callable=AsyncMock,
            side_effect=fake_run,
        ):
            result = await verify_macro_script(yaml_str)

        assert result.status == "success"
        assert isinstance(captured["script_input"], list)
        assert captured["script_input"][0]["event_type"] == "tap"
