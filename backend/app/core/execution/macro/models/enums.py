"""Macro verification enums models."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field
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
    PASSED = "passed"           # 按原计划执行成功
    ADAPTED = "adapted"         # 经修正后执行成功
    FAILED = "failed"           # 执行失败
    SKIPPED = "skipped"         # 被跳过
    TIMEOUT = "timeout"         # 超时
    REDUNDANT = "redundant"     # 被识别为冗余



class RedundancyType(str, Enum):
    """冗余类型"""
    LOW_VALUE_ACTION = "low_value_action"       # 低价值动作（如 mouse_move）
    DUPLICATE_ACTION = "duplicate_action"       # 重复动作
    UNNECESSARY_WAIT = "unnecessary_wait"       # 不必要的等待
    ORPHAN_ACTION = "orphan_action"             # 孤立的无效动作
    NONE = "none"
    UNKNOWN = "unknown"



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



