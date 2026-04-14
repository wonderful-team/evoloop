"""Macro verification report models."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import Field

from app.core.execution.macro.models.enums import VerificationStatus
from app.core.execution.macro.models.execution import StepResult
from app.infrastructure.pydantic_base import DynamicBaseModel


class RoundReport(DynamicBaseModel):
    """单轮验证报告"""
    round_number: int
    round_name: str
    status: VerificationStatus = VerificationStatus.PENDING

    total_steps: int = 0
    passed_steps: int = 0
    failed_steps: int = 0
    adapted_steps: int = 0
    skipped_steps: int = 0

    step_results: List[StepResult] = Field(default_factory=list)
    environment_snapshot: Optional[Dict[str, Any]] = None

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None



class ReportSummary(DynamicBaseModel):
    """报告汇总"""
    overall_success_rate: float = 0.0
    adaptation_rate: float = 0.0
    max_round_variance: float = 0.0
    average_execution_time_ms: int = 0
    total_anomalies_detected: int = 0
    total_adaptations_applied: int = 0

    # 冗余检测统计
    total_steps_checked: int = 0
    redundant_steps_count: int = 0
    redundant_steps_by_type: Dict[str, int] = Field(default_factory=dict)
    estimated_time_saved_ms: int = 0  # 跳过冗余步骤节省的时间



class VerificationIssue(DynamicBaseModel):
    """验证问题"""
    severity: str = "warning"  # critical / warning / info
    category: str = ""
    description: str = ""
    affected_steps: List[Union[int, str]] = Field(default_factory=list)
    suggestion: Optional[str] = None



class VerificationReport(DynamicBaseModel):
    """详细验证报告"""
    summary: ReportSummary = Field(default_factory=ReportSummary)
    rounds: List[RoundReport] = Field(default_factory=list)
    issues: List[VerificationIssue] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    optimization_stats: Optional[Dict[str, Any]] = None  # MacroOptimizer 统计信息



