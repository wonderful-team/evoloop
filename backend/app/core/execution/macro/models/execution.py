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
from app.core.execution.macro.schemas import RedundancyCheckResult, AdaptationRecord, ExecutionDetail, StepResult, MacroEvolutionRecord

