"""
Agent-based Macro Verification System

Phases 1-5 Complete Implementation

This module provides active verification of macros through real environment execution,
perception-first reasoning, macro evolution, and multi-round orchestration.
"""

from app.core.execution.macro.validator import AgentMacroValidator
from app.core.execution.macro.event.subscribers import MacroSelfHealingAdvisor
from app.core.execution.macro.evolution_engine import (
    AgenticTransformer,
    MacroEvolutionEngine,
    StepTransformer,
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
from app.core.execution.macro.schemas import EvolutionRule
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

    # Evolution engine (Phase 3)
    "MacroEvolutionEngine",
    "EvolutionRule",
    "StepTransformer",
    "AgenticTransformer",

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

    # Self-healing
    "MacroSelfHealingAdvisor",

    # Models
    "VerificationRequest",
    "VerificationResponse",
    "VerificationReport",
    "VerificationStatus",
    "EnvironmentConfig",
    "VerificationAgentConfig",
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
    "AnomalyType",
    "AIAnalysisResult",
    "RedundancyCheckResult",
    "RedundancyType",
]

__version__ = "1.1.0"
