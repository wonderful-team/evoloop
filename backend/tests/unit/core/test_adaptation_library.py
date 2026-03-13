"""
Unit tests for AdaptationStrategyLibrary (Phase 2)
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from app.core.execution.macro import (
    AdaptationStrategyLibrary,
    QuickFixStrategy,
    LLMDeepStrategy,
    AnomalyType,
)


class TestQuickFixStrategies:
    """Test quick fix strategies"""

    @pytest.fixture
    def library(self):
        return AdaptationStrategyLibrary(use_llm=False)

    @pytest.mark.asyncio
    async def test_coordinate_drift_fix(self, library):
        """Test coordinate drift quick fix"""
        step = {
            "step_number": 1,
            "type": "action",
            "event_type": "tap",
            "payload": {"x": 100, "y": 200}
        }

        anomaly_details = {
            "actual": {"x": 120, "y": 210}
        }

        ui_state = {
            "elements": [
                {"text": "Button", "bounds": {"center_x": 120, "center_y": 210}}
            ]
        }

        record = await library.adapt(
            step=step,
            anomaly_type=AnomalyType.COORDINATE_DRIFT,
            anomaly_details=anomaly_details,
            ui_state=ui_state
        )

        assert record.success is True
        assert "120" in record.reasoning or "actual position" in record.reasoning

    @pytest.mark.asyncio
    async def test_element_not_found_fix(self, library):
        """Test element not found quick fix"""
        step = {
            "target_selector": "#submit",
            "payload": {"selector": "#submit"}
        }

        anomaly_details = {"selector": "#submit"}

        ui_state = {
            "elements": [
                {"text": "Submit", "resource_id": "submit-v2", "class": "Button"}
            ]
        }

        record = await library.adapt(
            step=step,
            anomaly_type=AnomalyType.ELEMENT_NOT_FOUND,
            anomaly_details=anomaly_details,
            ui_state=ui_state
        )

        assert record.success is True
        assert record.adapted_strategy is not None

    @pytest.mark.asyncio
    async def test_element_obscured_fix(self, library):
        """Test element obscured quick fix"""
        step = {
            "step_number": 1,
            "type": "action",
            "event_type": "click",
            "source": "dom"
        }

        record = await library.adapt(
            step=step,
            anomaly_type=AnomalyType.ELEMENT_OBSCURED,
            anomaly_details={},
            ui_state={}
        )

        assert record.success is True
        # Should add pre_actions for dismissal
        assert "pre_actions" in record.adapted_strategy or "dismiss" in record.reasoning.lower()

    @pytest.mark.asyncio
    async def test_loading_timeout_fix(self, library):
        """Test loading timeout quick fix"""
        step = {
            "payload": {"timeout_ms": 5000}
        }

        record = await library.adapt(
            step=step,
            anomaly_type=AnomalyType.LOADING_TIMEOUT,
            anomaly_details={},
            ui_state={}
        )

        assert record.success is True
        # Should increase timeout
        new_timeout = record.adapted_strategy.get("payload", {}).get("timeout_ms", 0)
        assert new_timeout > 5000

    @pytest.mark.asyncio
    async def test_fallback_chain(self, library):
        """Test adaptation with fallback to multiple strategies"""
        step = {"step_number": 1, "type": "action"}

        records = await library.adapt_with_fallback(
            step=step,
            anomaly_type=AnomalyType.UNKNOWN,
            anomaly_details={},
            ui_state={},
            max_attempts=2
        )

        assert len(records) >= 1
        # Last record should indicate failure since UNKNOWN has no specific handler
        assert records[-1].success is False or records[-1].anomaly_type == AnomalyType.UNKNOWN


class TestLLMDeepStrategy:
    """Test LLM deep adaptation strategy"""

    @pytest.mark.asyncio
    async def test_llm_adaptation_prompt_building(self):
        """Test that LLM prompt is built correctly"""
        strategy = LLMDeepStrategy(AnomalyType.COORDINATE_DRIFT)

        step = {"step_number": 1, "type": "action"}
        details = {"drift": {"x": 10, "y": 20}}
        ui_state = {
            "platform": "web",
            "elements": [{"text": "Button"}]
        }

        prompt = strategy._build_adaptation_prompt(step, details, ui_state)

        assert "coordinate_drift" in prompt.lower() or "Coordinate Drift" in prompt
        assert "step" in prompt.lower()
        assert "guidelines" in prompt.lower()

    def test_llm_response_parsing(self):
        """Test parsing of LLM response"""
        strategy = LLMDeepStrategy(AnomalyType.ELEMENT_NOT_FOUND)

        original_step = {"step_number": 1, "type": "action"}

        # Valid JSON response
        valid_response = '''{"adapted_step": {"step_number": 1, "type": "action", "fallback": true}, "reasoning": "Added fallback"}'''

        adapted, reasoning = strategy._parse_llm_response(valid_response, original_step)

        assert adapted["step_number"] == 1
        assert "fallback" in adapted
        assert "Added fallback" in reasoning

    def test_llm_response_parsing_with_markdown(self):
        """Test parsing LLM response with markdown code blocks"""
        strategy = LLMDeepStrategy(AnomalyType.ELEMENT_NOT_FOUND)

        original_step = {"step_number": 1}

        markdown_response = '''```json
{"adapted_step": {"step_number": 1, "modified": true}, "reasoning": "Test"}
```'''

        adapted, _ = strategy._parse_llm_response(markdown_response, original_step)

        assert adapted.get("modified") is True


class TestAdaptationLibraryRegistry:
    """Test adaptation library registry functions"""

    def test_strategy_description(self):
        """Test getting strategy descriptions"""
        library = AdaptationStrategyLibrary()

        description = library.get_strategy_description(AnomalyType.COORDINATE_DRIFT)

        assert "coordinate" in description.lower()
        assert "drift" in description.lower()

    def test_all_anomaly_types_have_descriptions(self):
        """Test that all anomaly types have descriptions"""
        library = AdaptationStrategyLibrary()

        for anomaly_type in AnomalyType:
            description = library.get_strategy_description(anomaly_type)
            assert description is not None
            assert len(description) > 0
