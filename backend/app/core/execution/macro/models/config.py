"""Macro verification config models."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field
from app.infrastructure.pydantic_base import DynamicBaseModel

from app.core.execution.macro.models.enums import ExecutionMode

class EnvironmentConfig(DynamicBaseModel):
    """验证环境配置"""
    platform: str = "mobile"                       # web / android / desktop
    device_id: Optional[str] = None
    browser_config: Optional[Dict[str, Any]] = None
    resolution: Optional[tuple] = None
    extra_params: Dict[str, Any] = Field(default_factory=dict)



class RoundConfig(DynamicBaseModel):
    """单轮验证配置"""
    round_name: str = "default"
    environment_overrides: Dict[str, Any] = Field(default_factory=dict)
    inject_anomalies: List[str] = Field(default_factory=list)
    timeout_per_step: int = 30



class VerificationAgentConfig(DynamicBaseModel):
    """Agent 行为配置"""
    llm_model: str = "gpt-4o"
    max_retries_per_step: int = 3
    allow_strategy_adaptation: bool = True
    conservative_mode: bool = True  # Default to True to stop on failure
    enable_screenshot_analysis: bool = True



