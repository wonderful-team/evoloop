"""State sub-schemas for agent state tracking (react engine).

图引擎的 audit / sequential-workflow / deliverable 相关 schema 已随重构删除，
仅保留仍被使用的 HITL 授权请求模型 ``PendingApproval``。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class PendingApproval(DynamicBaseModel):
    """A HITL authorization request that is waiting for user response."""

    tool_name: str = ""
    tool_call_id: str = ""
    resource_path: str = ""
    action: str = ""
    risk_level: str = "medium"
    requested_at: str = ""  # ISO timestamp
    tool_args: dict[str, Any] = Field(default_factory=dict)
