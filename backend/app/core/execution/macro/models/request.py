"""Macro verification request models."""

from typing import List, Optional

from pydantic import Field

from app.core.execution.macro.models.config import EnvironmentConfig, RoundConfig, VerificationAgentConfig
from app.core.execution.macro.models.enums import ExecutionMode, VerificationStatus
from app.core.execution.macro.models.execution import MacroEvolutionRecord
from app.core.execution.macro.models.report import VerificationIssue, VerificationReport
from app.core.execution.macro.schema import MacroStep
from app.infrastructure.pydantic_base import DynamicBaseModel


class VerificationRequest(DynamicBaseModel):
    """验证请求"""
    macro_script: List[MacroStep]
    instructions: Optional[str] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None

    target_environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    max_rounds: int = 2
    round_configs: List[RoundConfig] = Field(default_factory=list)
    agent_config: Optional[VerificationAgentConfig] = None

    output_mode: str = "evolved"  # evolved / report_only



class VerificationResponse(DynamicBaseModel):
    """验证响应"""
    success: bool = False
    status: VerificationStatus = VerificationStatus.PENDING

    evolved_macro: Optional[List[MacroStep]] = None
    execution_mode: ExecutionMode = ExecutionMode.AGENTIC
    confidence_score: float = 0.0

    verification_report: VerificationReport = Field(default_factory=VerificationReport)
    evolution_records: List[MacroEvolutionRecord] = Field(default_factory=list)

    processing_time_seconds: float = 0.0
    rounds_completed: int = 0

    error_message: Optional[str] = None



class AIAnalysisResult(DynamicBaseModel):
    """Result of agentic analysis of verification data"""
    issues: List[VerificationIssue] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    recommended_execution_mode: ExecutionMode = ExecutionMode.AGENTIC
    confidence_score: float = 0.5
    qualitative_assessment: str = ""

