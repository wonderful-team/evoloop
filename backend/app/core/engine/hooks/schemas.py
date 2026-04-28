"""Hook system schemas."""

from typing import Any

from langchain_core.messages import BaseMessage
from pydantic import ConfigDict, Field

from app.core.engine.state.blackboard import BlackboardState
from app.infrastructure.pydantic_base import DynamicBaseModel


class HookMetadata(DynamicBaseModel):
    """Dynamic metadata for hook events."""
    summary: str | None = None
    audit_tier: str | None = None
    final_outcome: str | None = None
    duration_ms: float | None = None
    prompt: str | None = None


class ToolInput(DynamicBaseModel):
    """Typed wrapper for tool input arguments."""
    command: str | None = None
    path: str | None = None
    content: str | None = None
    query: str | None = None
    args: dict[str, Any] | None = None


class ToolResult(DynamicBaseModel):
    """Structured wrapper for tool execution results."""
    output: Any | None = None
    error: str | None = None
    data: dict[str, Any] | None = None


class HookContext(DynamicBaseModel):
    """Context passed to hook handlers."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str
    project_id: int | None = None
    user_id: str | None = None
    messages: list[BaseMessage] = Field(default_factory=list)
    blackboard: BlackboardState | None = None
    metadata: HookMetadata = Field(default_factory=HookMetadata)
    tool_name: str | None = None
    tool_input: ToolInput | None = None
    tool_result: ToolResult | None = None
    tool_use_id: str | None = None
    error: Exception | None = None
    error_message: str | None = None
    permission_mode: str | None = None
    compact_trigger: str | None = None
    memory_manager: Any | None = None
    memory_config: Any | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class HookResult(DynamicBaseModel):
    """Result from hook handler."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool = True
    block: bool = False
    retry: bool = False
    message: str | None = None
    modified_context: HookContext | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error: Exception | None = None
