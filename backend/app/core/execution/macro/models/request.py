"""Macro verification request models."""

from pydantic import Field

from app.core.execution.macro.models.config import (
    EnvironmentConfig,
    RoundConfig,
    VerificationAgentConfig,
)
from app.core.execution.macro.models.enums import ExecutionMode, VerificationStatus
from app.core.execution.macro.models.execution import MacroEvolutionRecord
from app.core.execution.macro.models.report import VerificationIssue, VerificationReport
from app.core.execution.macro.schema import MacroStep
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.core.execution.macro.schemas import VerificationRequest, VerificationResponse, AIAnalysisResult

