"""Top-level AgentState and StateUpdate models (react engine).

精简版：移除图架构的 ExecutionTicket / audit / subagent 编排 / workflow 字段。
DynamicBaseModel 的 extra=allow 保证旧序列化数据（含已删字段）仍可反序列化。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.core.engine.message.native_classes import BaseMessage
from app.infrastructure.pydantic_base import DynamicBaseModel


class AgentStateBase(DynamicBaseModel):
    # --- 1. Conversation ---
    messages: list[BaseMessage] = Field(default_factory=list)
    tool_history: list[str] = Field(default_factory=list)

    # --- 2. Execution ---
    thread_id: str | None = None
    project_id: int | None = None
    working_directory: str | None = None
    session_goal: str | None = None
    current_goal: str | None = None
    summary: str | None = None
    blocked_by_hook: bool | None = None

    # --- 3. Orchestration ---
    shared_context: dict[str, Any] = Field(default_factory=dict)

    # --- 4. Telemetry & Workspace ---
    error: str | None = None
    tool_memory: dict | None = None

    @property
    def metadata(self) -> dict[str, Any]:
        return self.build_metadata_dict()

    def build_metadata_dict(self) -> dict[str, Any]:
        fields = {
            "tool_history": self.tool_history,
            "tool_memory": self.tool_memory,
            "final_outcome": self.final_outcome if hasattr(self, "final_outcome") else None,
            "blocked_by_hook": self.blocked_by_hook,
        }
        return {k: v for k, v in fields.items() if v is not None}

    @property
    def blackboard(self) -> Any:
        return self


class AgentState(AgentStateBase):
    tool_history: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    project_id: int | None = None
    is_retry: bool | None = None
    iteration_count: int = 0
    session_goal: str | None = None
