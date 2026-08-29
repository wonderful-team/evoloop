"""Hook system schemas."""

from typing import Any

from pydantic import ConfigDict, Field

from app.core.engine.message.native_classes import BaseMessage
from app.core.security.path import (
    command_touches_project_metadata,
    is_project_metadata_path,
)
from app.infrastructure.pydantic_base import DynamicBaseModel

_METADATA_ARG_KEYS = (
    "AbsolutePath",
    "TargetFile",
    "SearchPath",
    "TargetDirectory",
    "DirectoryPath",
)


class HookMetadata(DynamicBaseModel):
    """Dynamic metadata for hook events."""

    summary: str | None = None
    audit_tier: str | None = None
    final_outcome: str | None = None
    duration_ms: float | None = None
    prompt: str | None = None
    intent_hint: Any | None = None
    source: str | None = None


class ToolInput(DynamicBaseModel):
    """Typed wrapper for tool input arguments."""

    command: str | None = None
    path: str | None = None
    content: str | None = None
    query: str | None = None
    args: dict[str, Any] | None = None

    def touches_project_metadata(self) -> bool:
        """Whether this tool call references project-local metadata (``.evoloop``).

        收集 path/args 结构化字段与 ``execute_command`` 命令文本，统一交给
        ``core.security.path`` 的判定函数裁决；全局 ``~/.evoloop`` 应用数据豁免。
        """
        if self.path and is_project_metadata_path(self.path):
            return True
        if self.args:
            for key in _METADATA_ARG_KEYS:
                val = self.args.get(key)
                if val and isinstance(val, str) and is_project_metadata_path(val):
                    return True
        if self.command and command_touches_project_metadata(self.command):
            return True
        return False


class ToolResult(DynamicBaseModel):
    """Structured wrapper for tool execution results."""

    output: Any | None = None
    error: str | None = None
    data: dict[str, Any] | None = None


class HookContext(DynamicBaseModel):
    """Context passed to hook handlers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    thread_id: str
    run_id: str | None = None
    project_id: int | None = None
    member_id: int | None = None
    messages: list[BaseMessage] = Field(default_factory=list)
    state: Any | None = None
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
