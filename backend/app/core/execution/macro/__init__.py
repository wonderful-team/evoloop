"""
Agent-based Macro Verification System

Phases 1-5 Complete Implementation

This module provides active verification of macros through real environment execution,
anomaly detection, strategy adaptation, macro evolution, and multi-round orchestration.

Usage:
    # High-level API
    from app.core.execution.macro import VerificationService

    result = await VerificationService.verify_macro(
        macro_script=macro_steps,
        platform="web",
        max_rounds=2
    )

    if result["success"]:
        evolved_macro = result["evolved_macro"]
        execution_mode = result["execution_mode"]

    # Low-level API
    from app.core.execution.macro import AgentMacroValidator, VerificationRequest

    request = VerificationRequest(
        macro_script=macro_steps,
        target_environment=EnvironmentConfig(platform="web"),
        max_rounds=2
    )

    validator = AgentMacroValidator(request)
    response = await validator.validate()
"""

from app.core.execution.macro.adaptation_library import (
    AdaptationStrategy,
    AdaptationStrategyLibrary,
    LLMDeepStrategy,
    QuickFixStrategy,
)
from app.core.execution.macro.agent_validator import AgentMacroValidator
from app.core.execution.macro.evolution_engine import (
    CoordinateDriftTransformer,
    ElementNotFoundTransformer,
    ElementObscuredTransformer,
    EvolutionRule,
    LoadingTimeoutTransformer,
    MacroEvolutionEngine,
    StateMismatchTransformer,
    StepTransformer,
)
from app.core.execution.macro.anomaly_detector import (
    AnomalyDetectionResult,
    AnomalyDetector,
)
from app.core.execution.macro.round_orchestrator import (
    BaselineStrategy,
    ChaosStrategy,
    CoordinateDriftInjector,
    DelayInjector,
    ElementInstabilityInjector,
    InterferenceInjector,
    InterferenceRegistry,
    NetworkDegradationInjector,
    PopupInterferenceInjector,
    ProgressiveDifficultyStrategy,
    RoundContext,
    RoundOrchestrator,
    RoundStrategy,
    StressTestStrategy,
)
from app.core.execution.macro.verification_models import (
    AdaptationRecord,
    AgentConfig,
    AnomalyType,
    EnvironmentConfig,
    ExecutionDetail,
    ExecutionMode,
    MacroEvolutionRecord,
    ReportSummary,
    RoundConfig,
    RoundReport,
    StepExecutionStatus,
    StepResult,
    VerificationIssue,
    VerificationReport,
    VerificationRequest,
    VerificationResponse,
    VerificationStatus,
)
from app.core.execution.macro.verification_reporter import (
    VerificationReporter,
    generate_comparison_report,
)
from app.core.execution.macro.verification_service import (
    MacroServiceIntegration,
    SynthesisIntegration,
    VerificationService,
    quick_verify,
    verify_macro,
)
from app.core.execution.macro.verification_worker import VerificationWorker

__all__ = [
    # Main validator
    "AgentMacroValidator",
    # Anomaly detection (Phase 1)
    "AnomalyDetector",
    "AnomalyDetectionResult",
    "AnomalyType",
    # Adaptation library (Phase 2)
    "AdaptationStrategyLibrary",
    "AdaptationStrategy",
    "QuickFixStrategy",
    "LLMDeepStrategy",
    # Evolution engine (Phase 3)
    "MacroEvolutionEngine",
    "EvolutionRule",
    "StepTransformer",
    "CoordinateDriftTransformer",
    "ElementNotFoundTransformer",
    "ElementObscuredTransformer",
    "LoadingTimeoutTransformer",
    "StateMismatchTransformer",
    # Round orchestration (Phase 4)
    "RoundOrchestrator",
    "RoundContext",
    "RoundStrategy",
    "BaselineStrategy",
    "StressTestStrategy",
    "ChaosStrategy",
    "ProgressiveDifficultyStrategy",
    "InterferenceInjector",
    "InterferenceRegistry",
    "DelayInjector",
    "NetworkDegradationInjector",
    "ElementInstabilityInjector",
    "PopupInterferenceInjector",
    "CoordinateDriftInjector",
    # Phase 5: Integration
    "VerificationService",
    "SynthesisIntegration",
    "MacroServiceIntegration",
    "verify_macro",
    "quick_verify",
    # Worker
    "VerificationWorker",
    # Reporter
    "VerificationReporter",
    "generate_comparison_report",
    # Models
    "VerificationRequest",
    "VerificationResponse",
    "VerificationReport",
    "VerificationStatus",
    "EnvironmentConfig",
    "AgentConfig",
    "RoundConfig",
    "RoundReport",
    "StepResult",
    "StepExecutionStatus",
    "AdaptationRecord",
    "ExecutionDetail",
    "MacroEvolutionRecord",
    "ExecutionMode",
    "ReportSummary",
    "VerificationIssue",
]

__version__ = "1.0.0"
