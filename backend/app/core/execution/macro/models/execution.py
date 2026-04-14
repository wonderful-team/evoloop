"""Macro verification execution models."""

from typing import Any

from pydantic import Field

from app.core.execution.macro.models.enums import (
    AnomalyType,
    RedundancyType,
    StepExecutionStatus,
)
from app.core.execution.macro.schema import MacroStep
from app.infrastructure.pydantic_base import DynamicBaseModel


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



