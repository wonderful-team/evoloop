"""Macro verification report models."""

from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.execution.macro.models.enums import VerificationStatus
from app.core.execution.macro.models.execution import StepResult
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.core.execution.macro.schemas import RoundReport, ReportSummary, VerificationIssue, VerificationReport
