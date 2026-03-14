"""
RoundOrchestrator - Phase 4: Multi-round Orchestration

Manages multiple verification rounds with interference injection.
Supports baseline, stress test, and chaos rounds.
"""

import copy
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from app.core.execution.macro.verification_models import (
    RoundConfig,
    RoundReport,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class InterferenceConfig:
    """Configuration for interference injection"""
    enabled: bool = False
    type: str = "none"  # none, delay, chaos, network_degradation
    intensity: float = 0.3  # 0.0 - 1.0
    targets: List[str] = field(default_factory=list)  # step types to target
    custom_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoundContext:
    """Context passed between rounds"""
    round_number: int
    previous_reports: List[RoundReport]
    shared_state: Dict[str, Any] = field(default_factory=dict)
    accumulated_anomalies: List[Dict[str, Any]] = field(default_factory=list)


class InterferenceInjector(ABC):
    """Abstract base for interference injectors"""

    @abstractmethod
    def get_name(self) -> str:
        """Get injector name"""
        pass

    @abstractmethod
    def can_apply(self, step: Dict[str, Any], context: RoundContext) -> bool:
        """Check if interference can be applied to this step"""
        pass

    @abstractmethod
    def apply(
        self,
        step: Dict[str, Any],
        context: RoundContext,
        intensity: float
    ) -> Dict[str, Any]:
        """
        Apply interference to a step

        Returns:
            Modified step with interference injected
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Get human-readable description"""
        pass


class DelayInjector(InterferenceInjector):
    """Inject delays at various points in execution"""

    def get_name(self) -> str:
        return "delay"

    def can_apply(self, step: Dict[str, Any], context: RoundContext) -> bool:
        # Can apply to any action step
        return step.get("type") == "action"

    def apply(
        self,
        step: Dict[str, Any],
        context: RoundContext,
        intensity: float
    ) -> Dict[str, Any]:
        modified = copy.deepcopy(step)
        payload = modified.get("payload", {})

        # Calculate delay based on intensity
        base_delay = 500  # ms
        max_additional = int(3000 * intensity)  # up to 3s additional
        delay = base_delay + random.randint(0, max_additional)

        # Add delay before this step
        payload["injected_delay_before_ms"] = delay
        payload["injected_interference"] = {
            "type": "delay",
            "duration_ms": delay,
            "description": f"Injected {delay}ms delay"
        }

        modified["payload"] = payload
        return modified

    def get_description(self) -> str:
        return "Adds random delays before step execution"


class NetworkDegradationInjector(InterferenceInjector):
    """Simulate slow network conditions"""

    def get_name(self) -> str:
        return "network_degradation"

    def can_apply(self, step: Dict[str, Any], context: RoundContext) -> bool:
        # Apply to navigation and loading steps
        event_type = step.get("event_type", "")
        return event_type in ("goto", "navigate", "wait", "wait_for")

    def apply(
        self,
        step: Dict[str, Any],
        context: RoundContext,
        intensity: float
    ) -> Dict[str, Any]:
        modified = copy.deepcopy(step)
        payload = modified.get("payload", {})

        # Increase timeout to account for slow network
        # Support both timeout_ms (browser) and duration_ms (mobile/wait steps)
        multiplier = 1 + (intensity * 2)  # 1x to 3x

        current_timeout = payload.get("timeout_ms", 5000)
        new_timeout = int(current_timeout * multiplier)
        payload["timeout_ms"] = new_timeout

        current_duration = payload.get("duration_ms", 5000)
        new_duration = int(current_duration * multiplier)
        payload["duration_ms"] = new_duration

        payload["simulated_network_speed"] = "slow-3g" if intensity > 0.7 else "fast-3g" if intensity > 0.3 else "4g"
        payload["injected_interference"] = {
            "type": "network_degradation",
            "timeout_multiplier": multiplier,
            "description": f"Simulated slow network ({payload['simulated_network_speed']})"
        }

        modified["payload"] = payload
        return modified

    def get_description(self) -> str:
        return "Simulates slow network conditions"


class ElementInstabilityInjector(InterferenceInjector):
    """Simulate dynamic/changing elements"""

    def get_name(self) -> str:
        return "element_instability"

    def can_apply(self, step: Dict[str, Any], context: RoundContext) -> bool:
        # Apply to element interaction steps
        event_type = step.get("event_type", "")
        return event_type in ("click", "tap", "input", "type_text")

    def apply(
        self,
        step: Dict[str, Any],
        context: RoundContext,
        intensity: float
    ) -> Dict[str, Any]:
        modified = copy.deepcopy(step)
        payload = modified.get("payload", {})

        # Add retry configuration
        base_retries = 1
        max_additional = int(4 * intensity)
        retries = base_retries + random.randint(0, max_additional)

        payload["max_retries"] = retries
        payload["retry_delay_ms"] = 500 + int(1000 * intensity)
        payload["injected_interference"] = {
            "type": "element_instability",
            "retries": retries,
            "description": f"Simulated element instability with {retries} retries"
        }

        modified["payload"] = payload
        return modified

    def get_description(self) -> str:
        return "Simulates unstable/dynamic UI elements"


class PopupInterferenceInjector(InterferenceInjector):
    """Simulate unexpected popups/modals"""

    def get_name(self) -> str:
        return "popup_interference"

    def can_apply(self, step: Dict[str, Any], context: RoundContext) -> bool:
        # Apply to some steps randomly
        return random.random() < 0.3  # 30% chance

    def apply(
        self,
        step: Dict[str, Any],
        context: RoundContext,
        intensity: float
    ) -> Dict[str, Any]:
        modified = copy.deepcopy(step)

        # Mark step as potentially having popup interference
        payload = modified.get("payload", {})
        payload["injected_interference"] = {
            "type": "popup_interference",
            "probability": intensity,
            "description": f"May encounter unexpected popup ({int(intensity * 100)}% chance)"
        }

        modified["payload"] = payload
        return modified

    def get_description(self) -> str:
        return "Simulates unexpected popups and modals"


class CoordinateDriftInjector(InterferenceInjector):
    """Simulate coordinate drift between recording and execution"""

    def get_name(self) -> str:
        return "coordinate_drift"

    def can_apply(self, step: Dict[str, Any], context: RoundContext) -> bool:
        # Apply to coordinate-based steps
        payload = step.get("payload", {})
        return payload.get("x") is not None and payload.get("y") is not None

    def apply(
        self,
        step: Dict[str, Any],
        context: RoundContext,
        intensity: float
    ) -> Dict[str, Any]:
        modified = copy.deepcopy(step)
        payload = modified.get("payload", {})

        # Apply drift to coordinates
        x = payload.get("x", 0)
        y = payload.get("y", 0)

        max_drift = int(50 * intensity)
        drift_x = random.randint(-max_drift, max_drift)
        drift_y = random.randint(-max_drift, max_drift)

        payload["x"] = x + drift_x
        payload["y"] = y + drift_y
        payload["original_x"] = x
        payload["original_y"] = y
        payload["injected_interference"] = {
            "type": "coordinate_drift",
            "drift": {"x": drift_x, "y": drift_y},
            "description": f"Applied coordinate drift ({drift_x:+d}, {drift_y:+d})"
        }

        modified["payload"] = payload
        return modified

    def get_description(self) -> str:
        return "Simulates coordinate drift between recording and execution"


class InterferenceRegistry:
    """Registry of available interference injectors"""

    _injectors: Dict[str, Type[InterferenceInjector]] = {
        "delay": DelayInjector,
        "network_degradation": NetworkDegradationInjector,
        "element_instability": ElementInstabilityInjector,
        "popup_interference": PopupInterferenceInjector,
        "coordinate_drift": CoordinateDriftInjector,
    }

    @classmethod
    def get_injector(cls, name: str) -> Optional[InterferenceInjector]:
        """Get injector by name"""
        injector_class = cls._injectors.get(name)
        return injector_class() if injector_class else None

    @classmethod
    def list_injectors(cls) -> List[str]:
        """List available injector names"""
        return list(cls._injectors.keys())

    @classmethod
    def register(cls, name: str, injector_class: Type[InterferenceInjector]) -> None:
        """Register a new injector"""
        cls._injectors[name] = injector_class


class RoundStrategy(ABC):
    """Abstract base for round strategies"""

    @abstractmethod
    def get_name(self) -> str:
        """Get strategy name"""
        pass

    @abstractmethod
    def configure_round(
        self,
        round_number: int,
        base_config: RoundConfig
    ) -> RoundConfig:
        """Configure the round based on strategy"""
        pass

    @abstractmethod
    def should_continue(
        self,
        current_round: int,
        reports: List[RoundReport]
    ) -> bool:
        """Determine if verification should continue to next round"""
        pass


class BaselineStrategy(RoundStrategy):
    """Baseline round - no interference, establish baseline"""

    def get_name(self) -> str:
        return "baseline"

    def configure_round(
        self,
        round_number: int,
        base_config: RoundConfig
    ) -> RoundConfig:
        config = copy.deepcopy(base_config)
        config.round_name = f"baseline_round_{round_number}"
        config.inject_anomalies = []
        return config

    def should_continue(
        self,
        current_round: int,
        reports: List[RoundReport]
    ) -> bool:
        # Always continue after baseline
        return True


class StressTestStrategy(RoundStrategy):
    """Stress test round - apply moderate interference"""

    def __init__(self, intensity: float = 0.5):
        self.intensity = intensity

    def get_name(self) -> str:
        return "stress_test"

    def configure_round(
        self,
        round_number: int,
        base_config: RoundConfig
    ) -> RoundConfig:
        config = copy.deepcopy(base_config)
        config.round_name = f"stress_test_{round_number}"
        config.inject_anomalies = [
            "delay",
            "element_instability",
            "network_degradation"
        ]
        config.timeout_per_step = int(base_config.timeout_per_step * 1.5)
        config.environment_overrides["interference_intensity"] = self.intensity
        return config

    def should_continue(
        self,
        current_round: int,
        reports: List[RoundReport]
    ) -> bool:
        # Continue if previous rounds had acceptable success rate
        if not reports:
            return True

        last_report = reports[-1]
        success_rate = last_report.passed_steps / max(last_report.total_steps, 1)
        return success_rate >= 0.5  # Continue if at least 50% success


class ChaosStrategy(RoundStrategy):
    """Chaos round - high interference, test robustness"""

    def __init__(self, intensity: float = 0.8):
        self.intensity = intensity

    def get_name(self) -> str:
        return "chaos"

    def configure_round(
        self,
        round_number: int,
        base_config: RoundConfig
    ) -> RoundConfig:
        config = copy.deepcopy(base_config)
        config.round_name = f"chaos_{round_number}"
        # All interference types
        config.inject_anomalies = InterferenceRegistry.list_injectors()
        config.timeout_per_step = int(base_config.timeout_per_step * 2)
        config.environment_overrides["interference_intensity"] = self.intensity
        config.environment_overrides["chaos_mode"] = True
        return config

    def should_continue(
        self,
        current_round: int,
        reports: List[RoundReport]
    ) -> bool:
        # Always continue - chaos round is final test
        return True


class ProgressiveDifficultyStrategy(RoundStrategy):
    """Each round increases difficulty based on previous results"""

    def get_name(self) -> str:
        return "progressive"

    def configure_round(
        self,
        round_number: int,
        base_config: RoundConfig
    ) -> RoundConfig:
        config = copy.deepcopy(base_config)

        # Increase intensity with each round
        intensity = min(0.3 * round_number, 1.0)

        config.round_name = f"progressive_{round_number}"
        config.inject_anomalies = InterferenceRegistry.list_injectors()[:round_number + 1]
        config.timeout_per_step = int(base_config.timeout_per_step * (1 + 0.2 * round_number))
        config.environment_overrides["interference_intensity"] = intensity

        return config

    def should_continue(
        self,
        current_round: int,
        reports: List[RoundReport]
    ) -> bool:
        # Continue if macro is adapting well
        if not reports:
            return True

        last_report = reports[-1]
        # Continue if we have some success or adaptations
        total_success = last_report.passed_steps + last_report.adapted_steps
        success_rate = total_success / max(last_report.total_steps, 1)
        return success_rate >= 0.3


class RoundOrchestrator:
    """
    Orchestrates multiple verification rounds with interference injection.

    Supports various round strategies and interference patterns.
    """

    def __init__(
        self,
        strategies: Optional[List[RoundStrategy]] = None,
        enable_interference: bool = True
    ):
        self.strategies = strategies or [
            BaselineStrategy(),
            StressTestStrategy(intensity=0.5),
            ChaosStrategy(intensity=0.7)
        ]
        self.enable_interference = enable_interference
        self.injectors: List[InterferenceInjector] = []

    def prepare_round(
        self,
        round_number: int,
        base_config: RoundConfig,
        macro_script: List[Dict[str, Any]],
        previous_reports: List[RoundReport]
    ) -> Tuple[RoundConfig, List[Dict[str, Any]]]:
        """
        Prepare a verification round

        Returns:
            Tuple of (round_config, modified_macro)
        """
        # Get strategy for this round
        strategy = self._get_strategy(round_number)

        # Configure round
        config = strategy.configure_round(round_number, base_config)

        # Apply interference if enabled
        modified_macro = macro_script
        if self.enable_interference and config.inject_anomalies:
            modified_macro = self._apply_interference(
                macro_script,
                config.inject_anomalies,
                config.environment_overrides.get("interference_intensity", 0.5),
                RoundContext(
                    round_number=round_number,
                    previous_reports=previous_reports
                )
            )

        logger.info(
            f"[Orchestrator] Prepared round {round_number} ({config.round_name}) "
            f"with {len(modified_macro)} steps"
        )

        return config, modified_macro

    def should_continue(
        self,
        current_round: int,
        reports: List[RoundReport]
    ) -> bool:
        """Determine if verification should continue"""
        strategy = self._get_strategy(current_round)
        should = strategy.should_continue(current_round, reports)

        if not should:
            logger.info(f"[Orchestrator] Strategy '{strategy.get_name()}' decided to stop after round {current_round}")

        return should

    def _get_strategy(self, round_number: int) -> RoundStrategy:
        """Get strategy for a round"""
        if round_number <= len(self.strategies):
            return self.strategies[round_number - 1]
        # Use last strategy for additional rounds
        return self.strategies[-1] if self.strategies else BaselineStrategy()

    def _apply_interference(
        self,
        macro_script: List[Dict[str, Any]],
        interference_types: List[str],
        intensity: float,
        context: RoundContext
    ) -> List[Dict[str, Any]]:
        """Apply interference to macro script"""
        modified = []

        # Get injectors
        injectors = []
        for itype in interference_types:
            injector = InterferenceRegistry.get_injector(itype)
            if injector:
                injectors.append(injector)

        # Apply to each step
        for step in macro_script:
            modified_step = copy.deepcopy(step)

            # Randomly apply injectors
            for injector in injectors:
                if injector.can_apply(modified_step, context):
                    # Apply based on intensity
                    if random.random() < intensity:
                        modified_step = injector.apply(modified_step, context, intensity)
                        logger.info(f"[Orchestrator] Applied {injector.get_name()} to step {step.get('step_number')}")

            modified.append(modified_step)

        return modified

    def generate_round_plan(
        self,
        max_rounds: int,
        base_config: RoundConfig
    ) -> List[RoundConfig]:
        """Generate a complete round plan"""
        plan = []

        for i in range(1, max_rounds + 1):
            strategy = self._get_strategy(i)
            config = strategy.configure_round(i, base_config)
            plan.append(config)

        return plan

    def get_interference_summary(self, macro_script: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get summary of interference applied to macro"""
        summary = {
            "total_steps": len(macro_script),
            "interfered_steps": 0,
            "interference_types": set(),
            "details": []
        }

        for step in macro_script:
            interference = step.get("payload", {}).get("injected_interference")
            if interference:
                summary["interfered_steps"] += 1
                summary["interference_types"].add(interference.get("type"))
                summary["details"].append({
                    "step_number": step.get("step_number"),
                    "interference": interference
                })

        summary["interference_types"] = list(summary["interference_types"])
        return summary
