"""
Unit tests for RoundOrchestrator (Phase 4)
"""

import pytest
from unittest.mock import Mock, patch

from app.core.execution.macro import (
    RoundOrchestrator,
    BaselineStrategy,
    StressTestStrategy,
    ChaosStrategy,
    ProgressiveDifficultyStrategy,
    InterferenceRegistry,
    DelayInjector,
    NetworkDegradationInjector,
    ElementInstabilityInjector,
    RoundConfig,
    RoundReport,
    RoundContext,
    VerificationStatus,
)


class TestRoundStrategies:
    """Test round strategies"""

    def test_baseline_strategy(self):
        """Test baseline strategy creates clean round"""
        strategy = BaselineStrategy()
        config = RoundConfig(round_name="test", timeout_per_step=30)

        result = strategy.configure_round(1, config)

        assert result.round_name == "baseline_round_1"
        assert result.inject_anomalies == []
        assert strategy.should_continue(1, [])

    def test_stress_test_strategy(self):
        """Test stress test strategy adds interference"""
        strategy = StressTestStrategy(intensity=0.5)
        config = RoundConfig(round_name="test", timeout_per_step=30)

        result = strategy.configure_round(2, config)

        assert "stress_test" in result.round_name
        assert len(result.inject_anomalies) > 0
        assert result.timeout_per_step == 45  # 1.5x
        assert result.environment_overrides.get("interference_intensity") == 0.5

    def test_stress_test_continue_logic(self):
        """Test stress test continue logic based on success rate"""
        strategy = StressTestStrategy()

        # High success rate - should continue
        report = Mock()
        report.passed_steps = 8
        report.total_steps = 10
        assert strategy.should_continue(1, [report]) is True

        # Low success rate - should stop
        report.passed_steps = 3
        report.total_steps = 10
        assert strategy.should_continue(1, [report]) is False

    def test_chaos_strategy(self):
        """Test chaos strategy adds all interference"""
        strategy = ChaosStrategy(intensity=0.9)
        config = RoundConfig(round_name="test", timeout_per_step=30)

        result = strategy.configure_round(1, config)

        assert "chaos" in result.round_name
        assert result.environment_overrides.get("chaos_mode") is True
        assert result.timeout_per_step == 60  # 2x

    def test_progressive_difficulty(self):
        """Test progressive difficulty increases with each round"""
        strategy = ProgressiveDifficultyStrategy()
        config = RoundConfig(round_name="test", timeout_per_step=30)

        round1 = strategy.configure_round(1, config)
        round2 = strategy.configure_round(2, config)
        round3 = strategy.configure_round(3, config)

        # Intensity should increase
        assert round1.environment_overrides["interference_intensity"] < \
               round2.environment_overrides["interference_intensity"]

        # Timeout should increase
        assert round1.timeout_per_step < round2.timeout_per_step < round3.timeout_per_step


class TestInterferenceInjectors:
    """Test interference injectors"""

    def test_delay_injector(self):
        """Test delay injector adds delays"""
        injector = DelayInjector()

        step = {"type": "action", "event_type": "click", "payload": {}}
        context = RoundContext(round_number=1, previous_reports=[])

        assert injector.can_apply(step, context) is True

        result = injector.apply(step, context, intensity=0.5)

        assert "injected_delay_before_ms" in result["payload"]
        assert result["payload"]["injected_interference"]["type"] == "delay"

    def test_network_degradation_injector(self):
        """Test network degradation injector"""
        injector = NetworkDegradationInjector()

        step = {"event_type": "goto", "payload": {"timeout_ms": 5000}}
        context = RoundContext(round_number=1, previous_reports=[])

        assert injector.can_apply(step, context) is True

        result = injector.apply(step, context, intensity=0.8)

        assert result["payload"]["timeout_ms"] > 5000
        assert "simulated_network_speed" in result["payload"]

    def test_element_instability_injector(self):
        """Test element instability injector"""
        injector = ElementInstabilityInjector()

        step = {"event_type": "click", "payload": {}}
        context = RoundContext(round_number=1, previous_reports=[])

        assert injector.can_apply(step, context) is True

        result = injector.apply(step, context, intensity=0.5)

        assert "max_retries" in result["payload"]
        assert "scroll_to_find" in result["payload"]

    def test_coordinate_drift_injector(self):
        """Test coordinate drift injector"""
        injector = CoordinateDriftInjector()

        step = {
            "event_type": "tap",
            "payload": {"x": 100, "y": 200}
        }
        context = RoundContext(round_number=1, previous_reports=[])

        assert injector.can_apply(step, context) is True

        result = injector.apply(step, context, intensity=0.5)

        # Coordinates should have drifted
        assert result["payload"]["x"] != 100 or result["payload"]["y"] != 200
        assert "original_x" in result["payload"]
        assert result["payload"]["injected_interference"]["type"] == "coordinate_drift"


class TestInterferenceRegistry:
    """Test interference registry"""

    def test_get_injector(self):
        """Test getting injectors from registry"""
        injector = InterferenceRegistry.get_injector("delay")

        assert injector is not None
        assert isinstance(injector, DelayInjector)

    def test_list_injectors(self):
        """Test listing available injectors"""
        injectors = InterferenceRegistry.list_injectors()

        assert "delay" in injectors
        assert "network_degradation" in injectors
        assert "coordinate_drift" in injectors


class TestRoundOrchestrator:
    """Test round orchestrator"""

    @pytest.fixture
    def sample_macro(self):
        return [
            {"step_number": 1, "type": "action", "event_type": "goto", "payload": {}},
            {"step_number": 2, "type": "action", "event_type": "click", "payload": {}},
            {"step_number": 3, "type": "action", "event_type": "wait", "payload": {"duration_ms": 1000}},
        ]

    @pytest.mark.asyncio
    async def test_prepare_baseline_round(self, sample_macro):
        """Test preparing baseline round"""
        orchestrator = RoundOrchestrator(
            strategies=[BaselineStrategy()],
            enable_interference=True
        )

        config, modified_macro = orchestrator.prepare_round(
            round_number=1,
            base_config=RoundConfig(round_name="test", timeout_per_step=30),
            macro_script=sample_macro,
            previous_reports=[]
        )

        assert config.round_name == "baseline_round_1"
        assert len(modified_macro) == len(sample_macro)
        # Baseline should not modify steps
        assert "injected_interference" not in modified_macro[0].get("payload", {})

    @pytest.mark.asyncio
    async def test_prepare_stress_test_round(self, sample_macro):
        """Test preparing stress test round with interference"""
        orchestrator = RoundOrchestrator(
            strategies=[StressTestStrategy(intensity=0.8)],
            enable_interference=True
        )

        config, modified_macro = orchestrator.prepare_round(
            round_number=1,
            base_config=RoundConfig(round_name="test", timeout_per_step=30),
            macro_script=sample_macro,
            previous_reports=[]
        )

        assert "stress_test" in config.round_name
        assert len(config.inject_anomalies) > 0

        # Check that interference was applied
        summary = orchestrator.get_interference_summary(modified_macro)
        assert summary["total_steps"] == len(sample_macro)

    @pytest.mark.asyncio
    async def test_interference_summary(self, sample_macro):
        """Test interference summary generation"""
        orchestrator = RoundOrchestrator(
            strategies=[ChaosStrategy(intensity=1.0)],
            enable_interference=True
        )

        config, modified_macro = orchestrator.prepare_round(
            round_number=1,
            base_config=RoundConfig(round_name="test", timeout_per_step=30),
            macro_script=sample_macro,
            previous_reports=[]
        )

        summary = orchestrator.get_interference_summary(modified_macro)

        assert summary["total_steps"] == len(sample_macro)
        assert isinstance(summary["interference_types"], list)
        assert isinstance(summary["details"], list)

    def test_generate_round_plan(self):
        """Test generating complete round plan"""
        orchestrator = RoundOrchestrator(
            strategies=[
                BaselineStrategy(),
                StressTestStrategy(),
                ChaosStrategy()
            ]
        )

        plan = orchestrator.generate_round_plan(
            max_rounds=3,
            base_config=RoundConfig(round_name="test", timeout_per_step=30)
        )

        assert len(plan) == 3
        assert "baseline" in plan[0].round_name
        assert "stress" in plan[1].round_name
        assert "chaos" in plan[2].round_name

    def test_should_continue_logic(self):
        """Test orchestrator continue logic"""
        orchestrator = RoundOrchestrator(
            strategies=[BaselineStrategy(), StressTestStrategy()]
        )

        # First round always continues
        assert orchestrator.should_continue(1, []) is True

        # Failed stress test should stop
        failed_report = Mock()
        failed_report.passed_steps = 2
        failed_report.total_steps = 10
        assert orchestrator.should_continue(2, [failed_report]) is False
