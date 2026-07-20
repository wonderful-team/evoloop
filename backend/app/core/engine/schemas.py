"""Core engine schemas — graph config, execution results, and operational models."""

from typing import Any

from pydantic import BaseModel, Field

from app.core.engine.message.native_classes import BaseMessage
from app.infrastructure.pydantic_base import DynamicBaseModel

# ---------------------------------------------------------------------------
# Graph Configuration (from schema.py)
# ---------------------------------------------------------------------------

class AggregateResult(DynamicBaseModel):
    status: str
    aggregated: Any


class NodeOutcome(DynamicBaseModel):
    """Structured outcome of a node execution."""
    status: str = "success"
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineResult(DynamicBaseModel):
    """Structured result from AgentEngine.run_node() and internal execution methods."""
    messages: list[BaseMessage] = Field(default_factory=list)
    tool_history: list[str] = Field(default_factory=list)
    is_truncated: bool = False
    signal: Any | None = None
    outcome: NodeOutcome | None = None
    # Additional signals that arrived in the same Supervisor turn and were queued.
    # Persisted into blackboard.pending_signals by handle_outcome so SupervisorNode
    # can drain them serially without re-running the LLM.
    queued_signals: list[Any] = Field(default_factory=list)


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
    name: str
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
        if self.recent_tools:
            recent_names = [f"{t.name}({t.token_count//1000}k)" for t in self.recent_tools[-5:]]
            lines.append(f"Recent tools: {', '.join(recent_names)}")
        if self.usage_ratio >= 0.80:
            lines.append("Tip: Use forget_tool_outputs to fold old exploration steps")
        return "\n".join(lines)

    def is_near_limit(self) -> bool:
        return self.usage_ratio >= 0.80

    def is_critical(self) -> bool:
        return self.usage_ratio >= 0.95


# ---------------------------------------------------------------------------
# Rewind Operations (from rewind/models.py)
# ---------------------------------------------------------------------------

class RewindOperation(DynamicBaseModel):
    """Request parameters for a rewind operation."""
    thread_id: str
    target_message_id: str | None = None
    include_target: bool = False
    revert_files: bool = True
    reset_state: bool = True
    reason: str = "user_request"


class RewindResult(DynamicBaseModel):
    """Result of a rewind operation."""
    status: str
    thread_id: str
    removed_message_count: int = 0
    reverted_file_count: int = 0
    removed_memory_count: int = 0
    removed_todo_count: int = 0
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
            "todos_removed": self.removed_todo_count,
            "traces_removed": self.removed_trace_count,
            "checkpoint_id": self.checkpoint_id,
            "errors": self.errors if self.errors else None,
        }


# ---------------------------------------------------------------------------
# Prompt Building (from prompts/supervisor_builder.py)
# ---------------------------------------------------------------------------

class SupervisorContext(DynamicBaseModel):
    """Formalized context structure for Supervisor decision making."""
    tools: list[Any]
    iteration_count: int
    last_human_msg: str | None
    state: Any
    structured_plan: str | dict | None = None
