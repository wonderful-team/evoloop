"""Core engine schemas — graph config, execution results, and operational models."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.engine.message.native_classes import BaseMessage
from app.infrastructure.pydantic_base import DynamicBaseModel


class RunOutcomeStatus(str, Enum):
    """Terminal status of a node execution outcome."""

    SUCCESS = "success"
    TRUNCATED = "truncated"
    ERROR = "error"
    FAILED = "failed"


class RunOutcome(DynamicBaseModel):
    """Structured outcome of a node execution."""

    status: RunOutcomeStatus = RunOutcomeStatus.SUCCESS
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineResult(DynamicBaseModel):
    """Structured result from AgentEngine.run_react_loop() and internal execution methods."""

    messages: list[BaseMessage] = Field(default_factory=list)
    tool_history: list[str] = Field(default_factory=list)
    is_truncated: bool = False
    outcome: RunOutcome | None = None


# ---------------------------------------------------------------------------
# Error Handling (from error_handler.py)
# ---------------------------------------------------------------------------


class ErrorClassification(BaseModel):
    """Structured error classification result."""

    error_type: str
    status_code: int | None = None
    title: str
    message: str
    hint: str
    raw_error: str
    is_terminal: bool = False


# ---------------------------------------------------------------------------
# Context Monitoring (from context_monitor.py)
# ---------------------------------------------------------------------------


class ToolCallInfo(DynamicBaseModel):
    """Information about a recent tool call."""

    tool_call_id: str
    name: str | None = None
    timestamp: float
    token_count: int


class ContextStats(DynamicBaseModel):
    """Context usage statistics for Agent awareness (token-based)."""

    total_tokens: int
    max_tokens: int
    message_count: int
    tool_message_count: int
    tool_tokens: int
    recent_tools: list[ToolCallInfo] = Field(default_factory=list)
    usage_ratio: float
    tools_tokens: int = 0
    basis: str = "estimated"

    def to_prompt(self) -> str:
        usage_pct = self.usage_ratio * 100
        if self.usage_ratio >= 0.95:
            status = "🔴 CRITICAL - Context nearly full!"
        elif self.usage_ratio >= 0.80:
            status = "⚠️  WARNING - Consider freeing space"
        else:
            status = "✅ OK"
        lines = [
            "[Context Monitor]",
            f"Usage: {self.total_tokens:,} / {self.max_tokens:,} tokens ({usage_pct:.0f}%) - {status}",
            f"Messages: {self.message_count} total, {self.tool_message_count} tool outputs ({self.tool_tokens:,} tokens)",
        ]
        if self.tools_tokens or self.basis == "measured":
            detail = f"Basis: {self.basis}"
            if self.tools_tokens:
                detail += f", tool surface ≈ {self.tools_tokens:,} tokens"
            lines.append(detail)
        if self.recent_tools:
            recent_names = [
                f"{t.name}({t.token_count // 1000}k)" for t in self.recent_tools[-5:]
            ]
            lines.append(f"Recent tools: {', '.join(recent_names)}")
        if self.usage_ratio >= 0.80:
            lines.append("Tip: 上下文由系统自动管理（超限工具输出自动折叠），无需手动折叠")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rewind Operations (from rewind/models.py)
# ---------------------------------------------------------------------------


class RewindResult(DynamicBaseModel):
    """Result of a rewind operation."""

    status: str
    thread_id: str
    removed_message_count: int = 0
    reverted_file_count: int = 0
    removed_memory_count: int = 0
    removed_trace_count: int = 0
    checkpoint_id: str | None = None
    errors: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "thread_id": self.thread_id,
            "removed_count": self.removed_message_count,
            "files_reverted": self.reverted_file_count,
            "memory_removed": self.removed_memory_count,
            "traces_removed": self.removed_trace_count,
            "checkpoint_id": self.checkpoint_id,
            "errors": self.errors if self.errors else None,
        }
