"""
Integration tests for VerificationService (Phase 5)
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from app.core.execution.macro import (
    VerificationService,
    SynthesisIntegration,
    MacroServiceIntegration,
)


class TestVerificationServiceIntegration:
    """Test VerificationService integration"""

    @pytest.fixture
    def sample_macro(self):
        return [
            {"step_number": 1, "type": "action", "event_type": "goto", "source": "dom", "payload": {"url": "https://test.com"}},
            {"step_number": 2, "type": "action", "event_type": "click", "source": "dom", "payload": {"selector": "#btn"}},
        ]

    @pytest.mark.asyncio
    async def test_verify_macro_full_flow(self, sample_macro):
        """Test complete verification flow"""
        # Mock validator
        mock_response = Mock()
        mock_response.success = True
        mock_response.status.value = "completed"
        mock_response.execution_mode.value = "deterministic"
        mock_response.confidence_score = 0.85
        mock_response.rounds_completed = 2
        mock_response.evolved_macro = sample_macro

        mock_report = Mock()
        mock_report.summary.overall_success_rate = 0.9
        mock_report.summary.adaptation_rate = 0.1
        mock_report.summary.total_anomalies_detected = 1
        mock_report.summary.total_adaptations_applied = 1
        mock_report.issues = []
        mock_report.recommendations = []

        mock_response.verification_report = mock_report

        with patch('app.core.execution.macro.AgentMacroValidator') as mock_validator_class:
            mock_validator = Mock()
            mock_validator.validate = AsyncMock(return_value=mock_response)
            mock_validator_class.return_value = mock_validator

            result = await VerificationService.verify_macro(
                macro_script=sample_macro,
                platform="web",
                max_rounds=2
            )

        assert result["success"] is True
        assert result["execution_mode"] == "deterministic"
        assert result["confidence_score"] == 0.85
        assert result["evolved_macro"] is not None

    @pytest.mark.asyncio
    async def test_verify_and_select_mode_deterministic(self, sample_macro):
        """Test mode selection for deterministic macro"""
        mock_response = Mock()
        mock_response.success = True
        mock_response.status.value = "completed"
        mock_response.execution_mode.value = "deterministic"
        mock_response.confidence_score = 0.9
        mock_response.verification_report.summary.overall_success_rate = 0.95

        with patch('app.core.execution.macro.AgentMacroValidator') as mock_validator_class:
            mock_validator = Mock()
            mock_validator.validate = AsyncMock(return_value=mock_response)
            mock_validator_class.return_value = mock_validator

            result = await VerificationService.verify_and_select_mode(
                macro_script=sample_macro,
                platform="web",
                confidence_threshold=0.8
            )

        assert result["can_execute"] is True
        assert result["recommended_mode"] == "deterministic"
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_verify_and_select_mode_agentic(self, sample_macro):
        """Test mode selection for problematic macro"""
        mock_response = Mock()
        mock_response.success = True
        mock_response.status.value = "partial_failed"
        mock_response.execution_mode.value = "agentic"
        mock_response.confidence_score = 0.4

        with patch('app.core.execution.macro.AgentMacroValidator') as mock_validator_class:
            mock_validator = Mock()
            mock_validator.validate = AsyncMock(return_value=mock_response)
            mock_validator_class.return_value = mock_validator

            result = await VerificationService.verify_and_select_mode(
                macro_script=sample_macro,
                platform="web",
                confidence_threshold=0.7
            )

        assert result["can_execute"] is True
        assert result["recommended_mode"] == "agentic"
        assert result["confidence"] == 0.4

    @pytest.mark.asyncio
    async def test_evolve_macro(self, sample_macro):
        """Test macro evolution"""
        evolved = sample_macro + [{"step_number": 3, "type": "wait", "payload": {}}]

        mock_response = Mock()
        mock_response.success = True
        mock_response.execution_mode.value = "hybrid"
        mock_response.confidence_score = 0.75
        mock_response.evolved_macro = evolved

        mock_report = Mock()
        mock_report.summary.adaptations_applied = 2
        mock_report.summary.anomalies_detected = 2
        mock_report.issues = []

        mock_response.verification_report = mock_report

        with patch('app.core.execution.macro.AgentMacroValidator') as mock_validator_class:
            mock_validator = Mock()
            mock_validator.validate = AsyncMock(return_value=mock_response)
            mock_validator_class.return_value = mock_validator

            result = await VerificationService.evolve_macro(
                macro_script=sample_macro,
                platform="web",
                max_rounds=2
            )

        assert result["success"] is True
        assert result["evolved_macro"] == evolved
        assert len(result["improvements"]) > 0


class TestSynthesisIntegration:
    """Test SynthesisIntegration"""

    @pytest.fixture
    def mobile_macro(self):
        return [
            {"step_number": 1, "type": "action", "source": "mobile", "event_type": "open_app", "payload": {"package_name": "com.test.app"}},
            {"step_number": 2, "type": "action", "source": "mobile", "event_type": "tap", "payload": {"x": 500, "y": 1000}},
        ]

    @pytest.mark.asyncio
    async def test_verify_for_synthesis_success(self, mobile_macro):
        """Test successful synthesis verification"""
        with patch('app.core.execution.macro.VerificationService.verify_macro') as mock_verify:
            mock_verify.return_value = {
                "success": True,
                "status": "completed",
                "execution_mode": "deterministic",
                "confidence_score": 0.9,
                "evolved_macro": mobile_macro,
                "verification_report": {"summary": {}}
            }

            result = await SynthesisIntegration.verify_for_synthesis(
                macro_script=mobile_macro,
                thread_id="test_thread",
                project_id=1
            )

        assert result["status"] == "success"
        assert result["execution_mode"] == "deterministic"
        assert result["evolved_macro"] == mobile_macro

    @pytest.mark.asyncio
    async def test_verify_for_synthesis_failure(self, mobile_macro):
        """Test failed synthesis verification"""
        with patch('app.core.execution.macro.VerificationService.verify_macro') as mock_verify:
            mock_verify.return_value = {
                "success": False,
                "error": "Verification failed",
                "verification_report": {}
            }

            result = await SynthesisIntegration.verify_for_synthesis(
                macro_script=mobile_macro,
                thread_id="test_thread",
                project_id=1
            )

        assert result["status"] == "failed"
        assert "error" in result

    def test_detect_platform(self):
        """Test platform detection from macro"""
        web_macro = [{"source": "dom"}]
        mobile_macro = [{"source": "mobile"}]
        desktop_macro = [{"source": "desktop"}]

        assert SynthesisIntegration._detect_platform(web_macro) == "web"
        assert SynthesisIntegration._detect_platform(mobile_macro) == "android"
        assert SynthesisIntegration._detect_platform(desktop_macro) == "desktop"


class TestMacroServiceIntegration:
    """Test MacroServiceIntegration"""

    @pytest.fixture
    def sample_macro(self):
        return [
            {"step_number": 1, "type": "action", "event_type": "goto", "payload": {}},
        ]

    @pytest.mark.asyncio
    async def test_execute_with_verification_high_confidence(self, sample_macro):
        """Test execution with high confidence verification"""
        with patch('app.core.execution.macro.VerificationService.verify_and_select_mode') as mock_verify:
            mock_verify.return_value = {
                "can_execute": True,
                "recommended_mode": "deterministic",
                "confidence": 0.9,
                "reason": "High confidence"
            }

            with patch('app.core.execution.macro.service.MacroService.run') as mock_run:
                mock_run.return_value = {"success": True}

                result = await MacroServiceIntegration.execute_with_verification(
                    thread_id="test_thread",
                    macro_script=sample_macro,
                    params={"platform": "web"},
                    verify_first=True
                )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_verification_low_confidence(self, sample_macro):
        """Test execution with low confidence adds supervision flag"""
        with patch('app.core.execution.macro.VerificationService.verify_and_select_mode') as mock_verify:
            mock_verify.return_value = {
                "can_execute": True,
                "recommended_mode": "agentic",
                "confidence": 0.4,
                "reason": "Low confidence"
            }

            captured_params = {}

            async def capture_run(thread_id, macro, params):
                captured_params.update(params)
                return {"success": True}

            with patch('app.core.execution.macro.service.MacroService.run', side_effect=capture_run):
                await MacroServiceIntegration.execute_with_verification(
                    thread_id="test_thread",
                    macro_script=sample_macro,
                    params={"platform": "web"},
                    verify_first=True,
                    confidence_threshold=0.7
                )

        assert captured_params.get("_require_agent_supervision") is True
        assert captured_params.get("_verification_confidence") == 0.4

    @pytest.mark.asyncio
    async def test_execute_without_verification(self, sample_macro):
        """Test execution bypassing verification"""
        with patch('app.core.execution.macro.service.MacroService.run') as mock_run:
            mock_run.return_value = {"success": True}

            result = await MacroServiceIntegration.execute_with_verification(
                thread_id="test_thread",
                macro_script=sample_macro,
                verify_first=False
            )

            mock_run.assert_called_once()
            assert result["success"] is True
