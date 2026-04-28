"""Schemas for macro module."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.core.execution.macro.schema import MacroScript, MacroStep
from app.infrastructure.pydantic_base import DynamicBaseModel


class VerificationStatus(str, Enum):
    """验证状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL_FAILED = "partial_failed"


class StepExecutionStatus(str, Enum):
    """单步执行状态"""
    PENDING = "pending"
    PASSED = "passed"  # 按原计划执行成功
    ADAPTED = "adapted"  # 经修正后执行成功
    FAILED = "failed"  # 执行失败
    SKIPPED = "skipped"  # 被跳过
    TIMEOUT = "timeout"  # 超时
    REDUNDANT = "redundant"  # 被识别为冗余


class RedundancyType(str, Enum):
    """冗余类型"""
    LOW_VALUE_ACTION = "low_value_action"  # 低价值动作（如 mouse_move）
    DUPLICATE_ACTION = "duplicate_action"  # 重复动作
    UNNECESSARY_WAIT = "unnecessary_wait"  # 不必要的等待
    ORPHAN_ACTION = "orphan_action"  # 孤立的无效动作
    NONE = "none"
    UNKNOWN = "unknown"


class AnomalyType(str, Enum):
    """异常类型"""
    COORDINATE_DRIFT = "coordinate_drift"  # 坐标漂移
    ELEMENT_NOT_FOUND = "element_not_found"  # 元素未找到
    ELEMENT_OBSCURED = "element_obscured"  # 元素被遮挡
    STATE_MISMATCH = "state_mismatch"  # 状态不匹配
    LOADING_TIMEOUT = "loading_timeout"  # 加载超时
    UNEXPECTED_FLOW = "unexpected_flow"  # 意外流程分支
    DATA_MISMATCH = "data_mismatch"  # 数据不匹配
    ENVIRONMENT_ERROR = "environment_error"  # 环境错误
    UNKNOWN = "unknown"  # 未知异常


class ExecutionMode(str, Enum):
    """执行模式"""
    DETERMINISTIC = "deterministic"  # 确定性执行
    HYBRID = "hybrid"  # 混合模式
    AGENTIC = "agentic"  # 完全 Agent 模式


class EnvironmentConfig(DynamicBaseModel):
    """验证环境配置"""
    platform: str = "mobile"  # web / android / desktop
    device_id: str | None = None
    browser_config: dict[str, Any] | None = None
    resolution: tuple | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)


class RoundConfig(DynamicBaseModel):
    """单轮验证配置"""
    round_name: str = "default"
    environment_overrides: dict[str, Any] = Field(default_factory=dict)
    inject_anomalies: list[str] = Field(default_factory=list)
    timeout_per_step: int = 30


class VerificationAgentConfig(DynamicBaseModel):
    """Agent 行为配置"""
    llm_model: str | None = None  # Must be provided explicitly
    max_retries_per_step: int = 3
    allow_strategy_adaptation: bool = True
    conservative_mode: bool = True  # Default to True to stop on failure
    enable_screenshot_analysis: bool = True


class EvolutionRule(DynamicBaseModel):
    """Rule for transforming a step based on anomaly type"""
    name: str
    anomaly_type: AnomalyType
    description: str
    priority: int = 0


class EvolutionContext(DynamicBaseModel):
    """Context for macro evolution"""
    original_macro: list[dict[str, Any]]
    step_results: list[StepResult]
    evolution_records: list[MacroEvolutionRecord]
    target_platform: str = "web"

    # Track which steps have been modified
    modified_steps: set[int] = Field(default_factory=set)

    # Track added steps (insertions)
    inserted_steps: dict[int, list[dict[str, Any]]] = Field(default_factory=dict)


class HealingDecision(DynamicBaseModel):
    """Result of a self-healing policy check."""
    allowed: bool
    reason: str
    # Source of the decision for debugging
    source: str  # "global" | "skill" | "execution" | "allowed"


class RedundancyCheckResult(DynamicBaseModel):
    """冗余检查结果"""
    is_redundant: bool = False
    redundancy_type: RedundancyType = RedundancyType.UNKNOWN
    reason: str = ""
    similar_to_step: int | None = None  # 如果是重复的，指向哪个步骤
    suggested_action: str = "keep"  # keep / skip / merge / remove


class AdaptationRecord(DynamicBaseModel):
    """修正记录

    支持步骤修改和额外步骤插入：
    - adapted_strategy: 修改后的主步骤
    - additional_steps: 额外添加的步骤（如前置等待、弹窗关闭等）
    """
    anomaly_type: AnomalyType = AnomalyType.UNKNOWN
    original_strategy: MacroStep = Field(default_factory=lambda: MacroStep(type="action"))
    adapted_strategy: MacroStep = Field(default_factory=lambda: MacroStep(type="action"))
    reasoning: str = ""
    success: bool = False
    attempt_number: int = 1

    # 额外步骤（在 adapted_strategy 之前执行）
    additional_steps: list[MacroStep] = Field(default_factory=list)


class ExecutionDetail(DynamicBaseModel):
    """执行详情"""
    pre_state: dict[str, Any] | None = None
    action_taken: MacroStep = Field(default_factory=lambda: MacroStep(type="action"))
    post_state: dict[str, Any] | None = None
    screenshot_path: str | None = None
    ui_dump: dict[str, Any] | None = None


class StepResult(DynamicBaseModel):
    """单步执行结果"""
    step_number: int
    original_step: MacroStep = Field(default_factory=lambda: MacroStep(type="action"))
    status: StepExecutionStatus = StepExecutionStatus.PENDING

    execution: ExecutionDetail | None = None
    adaptations: list[AdaptationRecord] = Field(default_factory=list)

    execution_time_ms: int = 0
    error_message: str | None = None

    # 修正后的实际执行参数（用于宏进化）
    effective_parameters: MacroStep | None = None

    # 冗余检查信息
    redundancy_check: RedundancyCheckResult | None = None


class MacroEvolutionRecord(DynamicBaseModel):
    """宏进化记录

    支持步骤修改和额外步骤插入：
    - evolved_step: 修改后的主步骤
    - additional_steps: 额外添加的步骤（如前置等待、弹窗关闭等）
    """
    original_step: MacroStep
    evolved_step: MacroStep
    evolution_reason: str
    confidence: float = 1.0

    # 额外步骤（在 evolved_step 之前执行）
    additional_steps: list[MacroStep] = Field(default_factory=list)


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

    step_results: list[StepResult] = Field(default_factory=list)
    environment_snapshot: dict[str, Any] | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None


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
    redundant_steps_by_type: dict[str, int] = Field(default_factory=dict)
    estimated_time_saved_ms: int = 0  # 跳过冗余步骤节省的时间


class VerificationIssue(DynamicBaseModel):
    """验证问题"""
    severity: str = "warning"  # critical / warning / info
    category: str = ""
    description: str = ""
    affected_steps: list[int | str] = Field(default_factory=list)
    suggestion: str | None = None


class VerificationReport(DynamicBaseModel):
    """详细验证报告"""
    summary: ReportSummary = Field(default_factory=ReportSummary)
    rounds: list[RoundReport] = Field(default_factory=list)
    issues: list[VerificationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    optimization_stats: dict[str, Any] | None = None  # MacroOptimizer 统计信息


class VerificationRequest(DynamicBaseModel):
    """验证请求"""
    macro_script: list[MacroStep]
    instructions: str | None = None
    session_id: str | None = None
    thread_id: str | None = None

    target_environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    max_rounds: int = 2
    round_configs: list[RoundConfig] = Field(default_factory=list)
    agent_config: VerificationAgentConfig | None = None

    output_mode: str = "evolved"  # evolved / report_only


class VerificationResponse(DynamicBaseModel):
    """验证响应"""
    success: bool = False
    status: VerificationStatus = VerificationStatus.PENDING

    evolved_macro: list[MacroStep] | None = None
    execution_mode: ExecutionMode = ExecutionMode.AGENTIC
    confidence_score: float = 0.0

    verification_report: VerificationReport = Field(default_factory=VerificationReport)
    evolution_records: list[MacroEvolutionRecord] = Field(default_factory=list)

    processing_time_seconds: float = 0.0
    rounds_completed: int = 0

    error_message: str | None = None


class AIAnalysisResult(DynamicBaseModel):
    """Result of agentic analysis of verification data"""
    issues: list[VerificationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    recommended_execution_mode: ExecutionMode = ExecutionMode.AGENTIC
    confidence_score: float = 0.5
    qualitative_assessment: str = ""


class OptimizationResult(DynamicBaseModel):
    original_steps: int
    optimized_steps: int
    removed_steps: int
    merged_steps: int
    time_saved_ms: int
    strategies_applied: list[str] = Field(default_factory=list)

    @property
    def reduction_ratio(self) -> float:
        if self.original_steps == 0: return 0.0
        return (self.original_steps - self.optimized_steps) / self.original_steps


class ActionDecision(DynamicBaseModel):
    """Decision made by the reasoning engine"""
    action: str  # 'execute', 'correct', 'skip', 'retry', 'abort'
    reasoning: str
    suggested_step: dict[str, Any] | None = None
    additional_steps: list[dict[str, Any]] = []
    confidence: float


class InterferenceConfig(DynamicBaseModel):
    """Configuration for interference injection"""
    enabled: bool = False
    type: str = "none"  # none, delay, chaos, network_degradation
    intensity: float = 0.3  # 0.0 - 1.0
    targets: list[str] = Field(default_factory=list)  # step types to target
    custom_params: dict[str, Any] = Field(default_factory=dict)


class RoundContext(DynamicBaseModel):
    """Context passed between rounds"""
    round_number: int
    previous_reports: list[RoundReport]
    shared_state: dict[str, Any] = Field(default_factory=dict)
    accumulated_anomalies: list[dict[str, Any]] = Field(default_factory=list)


class MacroRunResult(DynamicBaseModel):
    success: bool
    message: str
    extracted_data: dict[str, Any] | None = None
    allow_self_healing: bool | None = None
    healing_disabled_reason: str | None = None
    healing_disabled_source: str | None = None
    suggestions: list[str] | None = None
    status: str | None = None  # e.g. "fallback_required"
    fallback_context: dict[str, Any] | None = None


class VerificationSummary(DynamicBaseModel):
    success_rate: float
    adaptation_rate: float
    anomalies_detected: int
    adaptations_applied: int


class ModeRecommendation(DynamicBaseModel):
    can_execute: bool
    recommended_mode: str
    reason: str
    confidence: float


class MacroEvolutionResult(DynamicBaseModel):
    success: bool
    original_macro: list[dict[str, Any]] | MacroScript | str
    evolved_macro: list[dict[str, Any]] | None = None
    execution_mode: str | None = None
    confidence: float | None = None
    improvements: list[str] = Field(default_factory=list)
    report: VerificationReport | None = None
    error: str | None = None
