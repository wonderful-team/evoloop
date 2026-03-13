"""
Agent 宏验证数据模型

定义验证过程中的所有数据结构
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


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
    PASSED = "passed"           # 按原计划执行成功
    ADAPTED = "adapted"         # 经修正后执行成功
    FAILED = "failed"           # 执行失败
    SKIPPED = "skipped"         # 被跳过
    TIMEOUT = "timeout"         # 超时


class AnomalyType(str, Enum):
    """异常类型"""
    COORDINATE_DRIFT = "coordinate_drift"           # 坐标漂移
    ELEMENT_NOT_FOUND = "element_not_found"         # 元素未找到
    ELEMENT_OBSCURED = "element_obscured"           # 元素被遮挡
    STATE_MISMATCH = "state_mismatch"               # 状态不匹配
    LOADING_TIMEOUT = "loading_timeout"             # 加载超时
    UNEXPECTED_FLOW = "unexpected_flow"             # 意外流程分支
    DATA_MISMATCH = "data_mismatch"                 # 数据不匹配
    ENVIRONMENT_ERROR = "environment_error"         # 环境错误
    UNKNOWN = "unknown"                             # 未知异常


class ExecutionMode(str, Enum):
    """执行模式"""
    DETERMINISTIC = "deterministic"     # 确定性执行
    HYBRID = "hybrid"                   # 混合模式
    AGENTIC = "agentic"                 # 完全 Agent 模式


class EnvironmentConfig(BaseModel):
    """验证环境配置"""
    platform: str = "mobile"                       # web / android / desktop
    device_id: Optional[str] = None
    browser_config: Optional[Dict[str, Any]] = None
    resolution: Optional[tuple] = None
    extra_params: Dict[str, Any] = Field(default_factory=dict)


class RoundConfig(BaseModel):
    """单轮验证配置"""
    round_name: str = "default"
    environment_overrides: Dict[str, Any] = Field(default_factory=dict)
    inject_anomalies: List[str] = Field(default_factory=list)
    timeout_per_step: int = 30


class AgentConfig(BaseModel):
    """Agent 行为配置"""
    llm_model: str = "gpt-4o"
    max_retries_per_step: int = 3
    allow_strategy_adaptation: bool = True
    conservative_mode: bool = False
    enable_screenshot_analysis: bool = True


class VerificationRequest(BaseModel):
    """验证请求"""
    macro_script: List[Dict[str, Any]]
    instructions: Optional[str] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None

    target_environment: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    max_rounds: int = 2
    round_configs: List[RoundConfig] = Field(default_factory=list)
    agent_config: Optional[AgentConfig] = None

    output_mode: str = "evolved"  # evolved / report_only


class AdaptationRecord(BaseModel):
    """修正记录"""
    anomaly_type: AnomalyType = AnomalyType.UNKNOWN
    original_strategy: Dict[str, Any] = Field(default_factory=dict)
    adapted_strategy: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    success: bool = False
    attempt_number: int = 1


class ExecutionDetail(BaseModel):
    """执行详情"""
    pre_state: Optional[Dict[str, Any]] = None
    action_taken: Dict[str, Any] = Field(default_factory=dict)
    post_state: Optional[Dict[str, Any]] = None
    screenshot_path: Optional[str] = None
    ui_dump: Optional[Dict[str, Any]] = None


class StepResult(BaseModel):
    """单步执行结果"""
    step_number: int
    original_step: Dict[str, Any] = Field(default_factory=dict)
    status: StepExecutionStatus = StepExecutionStatus.PENDING

    execution: Optional[ExecutionDetail] = None
    adaptations: List[AdaptationRecord] = Field(default_factory=list)

    execution_time_ms: int = 0
    error_message: Optional[str] = None

    # 修正后的实际执行参数（用于宏进化）
    effective_parameters: Optional[Dict[str, Any]] = None


class RoundReport(BaseModel):
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


class ReportSummary(BaseModel):
    """报告汇总"""
    overall_success_rate: float = 0.0
    adaptation_rate: float = 0.0
    max_round_variance: float = 0.0
    average_execution_time_ms: int = 0
    total_anomalies_detected: int = 0
    total_adaptations_applied: int = 0


class VerificationIssue(BaseModel):
    """验证问题"""
    severity: str = "warning"  # critical / warning / info
    category: str = ""
    description: str = ""
    affected_steps: List[int] = Field(default_factory=list)
    suggestion: Optional[str] = None


class VerificationReport(BaseModel):
    """详细验证报告"""
    summary: ReportSummary = Field(default_factory=ReportSummary)
    rounds: List[RoundReport] = Field(default_factory=list)
    issues: List[VerificationIssue] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class MacroEvolutionRecord(BaseModel):
    """宏进化记录"""
    original_step: Dict[str, Any]
    evolved_step: Dict[str, Any]
    evolution_reason: str
    confidence: float = 1.0


class VerificationResponse(BaseModel):
    """验证响应"""
    success: bool = False
    status: VerificationStatus = VerificationStatus.PENDING

    evolved_macro: Optional[List[Dict[str, Any]]] = None
    execution_mode: ExecutionMode = ExecutionMode.AGENTIC
    confidence_score: float = 0.0

    verification_report: VerificationReport = Field(default_factory=VerificationReport)
    evolution_records: List[MacroEvolutionRecord] = Field(default_factory=list)

    processing_time_seconds: float = 0.0
    rounds_completed: int = 0

    error_message: Optional[str] = None
