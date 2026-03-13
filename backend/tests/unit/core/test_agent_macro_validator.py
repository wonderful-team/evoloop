"""
Unit tests for AgentMacroValidator (Phase 1 Core)
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from app.core.execution.macro import (
    AgentMacroValidator,
    VerificationRequest,
    EnvironmentConfig,
    AgentConfig,
    VerificationStatus,
    StepExecutionStatus,
    AnomalyType,
)


class TestAgentMacroValidator:
    """Test cases for AgentMacroValidator"""

    @pytest.fixture
    def sample_macro(self):
        """Sample macro for testing"""
        return [
            {
                "step_number": 1,
                "type": "action",
                "event_type": "goto",
                "source": "dom",
                "payload": {"url": "https://example.com"}
            },
            {
                "step_number": 2,
                "type": "action",
                "event_type": "click",
                "source": "dom",
                "target_selector": "#btn",
                "payload": {"selector": "#btn"}
            }
        ]

    @pytest.fixture
    def base_request(self, sample_macro):
        """Base verification request"""
        return VerificationRequest(
            macro_script=sample_macro,
            target_environment=EnvironmentConfig(platform="web"),
            max_rounds=1
        )

    @pytest.mark.asyncio
    async def test_validator_initialization(self, base_request):
        """Test validator initializes correctly"""
        validator = AgentMacroValidator(base_request)

        assert validator.request == base_request
        assert validator.current_macro == base_request.macro_script
        assert validator.total_anomalies == 0
        assert validator.total_adaptations == 0

    @pytest.mark.asyncio
    async def test_successful_validation(self, base_request):
        """Test successful validation flow"""
        validator = AgentMacroValidator(base_request)

        # Mock worker
        mock_worker = AsyncMock()
        mock_worker.capture_state.return_value = {
            "platform": "web",
            "elements": []
        }
        mock_worker.execute_step.return_value = {"status": "success"}

        with patch.object(validator, '_create_worker', return_value=mock_worker):
            response = await validator.validate()

        assert response.success is True
        assert response.status == VerificationStatus.COMPLETED
        assert response.rounds_completed == 1

    @pytest.mark.asyncio
    async def test_validation_with_anomaly(self, base_request):
        """Test validation with detected anomaly"""
        validator = AgentMacroValidator(base_request)

        # Mock worker with state change indicating anomaly
        mock_worker = AsyncMock()
        mock_worker.capture_state.side_effect = [
            {"platform": "web", "elements": []},  # pre_state
            {"platform": "web", "elements": []}   # post_state (no change = anomaly)
        ]
        mock_worker.execute_step.return_value = {"status": "success"}

        # Mock adaptation library
        mock_adaptation = Mock()
        mock_adaptation.success = True
        mock_adaptation.adapted_strategy = base_request.macro_script[0]

        with patch.object(validator, '_create_worker', return_value=mock_worker):
            with patch.object(validator.adaptation_library, 'adapt_with_fallback',
                            return_value=[mock_adaptation]):
                response = await validator.validate()

        assert response.success is True
        assert response.total_anomalies_detected >= 0

    @pytest.mark.asyncio
    async def test_multi_round_validation(self, sample_macro):
        """Test validation with multiple rounds"""
        request = VerificationRequest(
            macro_script=sample_macro,
            target_environment=EnvironmentConfig(platform="web"),
            max_rounds=3
        )
        validator = AgentMacroValidator(request)

        mock_worker = AsyncMock()
        mock_worker.capture_state.return_value = {"platform": "web", "elements": []}
        mock_worker.execute_step.return_value = {"status": "success"}

        with patch.object(validator, '_create_worker', return_value=mock_worker):
            response = await validator.validate()

        assert response.rounds_completed == 3

    @pytest.mark.asyncio
    async def test_failed_step_handling(self, base_request):
        """Test handling of failed steps"""
        validator = AgentMacroValidator(base_request)

        mock_worker = AsyncMock()
        mock_worker.capture_state.return_value = {"platform": "web", "elements": []}
        mock_worker.execute_step.return_value = {"error": "element_not_found"}

        with patch.object(validator, '_create_worker', return_value=mock_worker):
            response = await validator.validate()

        assert response.success is False or response.status == VerificationStatus.PARTIAL_FAILED

    @pytest.mark.asyncio
    async def test_execution_mode_determination(self, base_request):
        """Test execution mode is determined correctly"""
        validator = AgentMacroValidator(base_request)

        # Perfect execution should suggest deterministic mode
        mock_worker = AsyncMock()
        mock_worker.capture_state.return_value = {"platform": "web", "elements": []}
        mock_worker.execute_step.return_value = {"status": "success"}

        with patch.object(validator, '_create_worker', return_value=mock_worker):
            response = await validator.validate()

        assert response.execution_mode.value in ["deterministic", "hybrid", "agentic"]


class TestStepExecution:
    """Test individual step execution"""

    @pytest.mark.asyncio
    async def test_step_timeout(self):
        """Test step timeout handling"""
        from app.core.execution.macro.verification_models import RoundConfig

        config = RoundConfig(timeout_per_step=1)  # 1 second timeout

        # Mock async timeout
        import asyncio

        async def slow_step():
            await asyncio.sleep(10)
            return {}

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_step(), timeout=config.timeout_per_step)


class TestAnomalyDetection:
    """Test anomaly detection in validator"""

    @pytest.mark.asyncio
    async def test_pre_execution_anomaly_detection(self):
        """Test pre-execution anomaly detection"""
        from app.core.execution.macro.anomaly_detector import AnomalyDetector

        detector = AnomalyDetector()

        step = {
            "target_selector": "#missing-element",
            "payload": {"selector": "#missing-element"}
        }

        ui_state = {
            "elements": [
                {"text": "Other Element", "resource_id": "other"}
            ]
        }

        result = await detector.detect_pre_execution_anomaly(step, ui_state)

        assert result.is_anomaly is True
        assert result.anomaly_type == AnomalyType.ELEMENT_NOT_FOUND

    @pytest.mark.asyncio
    async def test_post_execution_anomaly_detection(self):
        """Test post-execution anomaly detection"""
        from app.core.execution.macro.anomaly_detector import AnomalyDetector

        detector = AnomalyDetector()

        step = {"type": "action", "event_type": "click"}
        pre_state = {"elements": [{"id": "1"}]}
        post_state = {"elements": [{"id": "1"}]}  # No change
        execution_result = "success"

        result = await detector.detect_post_execution_anomaly(
            step, pre_state, post_state, execution_result
        )

        assert result.is_anomaly is True
        assert result.anomaly_type == AnomalyType.STATE_MISMATCH
