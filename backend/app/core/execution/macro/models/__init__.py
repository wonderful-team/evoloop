"""Macro verification models package."""

from app.core.execution.macro.models.config import (
    EnvironmentConfig,
    RoundConfig,
    VerificationAgentConfig,
)
from app.core.execution.macro.models.enums import (
    AnomalyType,
    ExecutionMode,
    RedundancyType,
    StepExecutionStatus,
    VerificationStatus,
)
from app.core.execution.macro.models.execution import (
    AdaptationRecord,
    ExecutionDetail,
    MacroEvolutionRecord,
    RedundancyCheckResult,
    StepResult,
)
from app.core.execution.macro.models.report import (
    ReportSummary,
    RoundReport,
    VerificationIssue,
    VerificationReport,
)
from app.core.execution.macro.models.request import (
    AIAnalysisResult,
    VerificationRequest,
    VerificationResponse,
)
