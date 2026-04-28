"""Core engine schemas — graph config, execution results, and operational models."""

from typing import Any, Literal, Optional
from datetime import datetime

from pydantic import BaseModel, Field, model_validator, ConfigDict

from app.infrastructure.pydantic_base import DynamicBaseModel
from app.core.engine.state.blackboard import BlackboardState
from app.core.engine.state.blackboard import SpawnPlan
from app.core.engine.state.config import AgentRuntimeConfig


# ---------------------------------------------------------------------------
# Graph Configuration (from schema.py)
# ---------------------------------------------------------------------------

class AggregateResult(DynamicBaseModel):
    status: str
    aggregated: Any


class NodeConfigPayload(DynamicBaseModel):
    intent: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)


class EdgeCondition(DynamicBaseModel):
    expr: str
    to: str


class NodeConfig(DynamicBaseModel):
    """Configuration for a graph node."""
    id: str
    xpath: str | None = Field(alias="path", default=None)
    type: Literal["function", "generic"] = "function"

    @property
    def path(self):
        return self.xpath

    config: NodeConfigPayload | None = Field(default_factory=NodeConfigPayload)
    tools: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_node_type(self) -> "NodeConfig":
        if not self.xpath:
            raise ValueError(f"Node '{self.id}' is missing 'path'")
        return self


class EdgeConfig(DynamicBaseModel):
    """Configuration for a graph edge."""
    from_node: str = Field(alias="from")
    to_node: str | None = Field(alias="to", default=None)
    type: Literal["simple", "conditional"] = "simple"
    router: str | None = None
    map: dict[str, str] | None = None
    conditions: list[EdgeCondition] | None = None
    default: str | None = None

    @model_validator(mode="after")
    def validate_edge_type(self) -> "EdgeConfig":
        if self.type == "simple" and not self.to_node:
            raise ValueError(f"Simple edge from '{self.from_node}' is missing 'to' field")
        if self.type == "conditional" and not (self.router or self.conditions):
            raise ValueError(f"Conditional edge from '{self.from_node}' must have either 'router' or 'conditions'")
        return self


class AgentGraphConfig(DynamicBaseModel):
    """Configuration for an agent graph."""
    name: str
    version: str
    state_schema: str = "app.core.engine.state.AgentState"
    nodes: list[NodeConfig]
    edges: list[EdgeConfig]
    interrupt_before: list[str] = Field(default_factory=list)
    interrupt_after: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph_connectivity(self) -> "AgentGraphConfig":
        node_ids = {node.id for node in self.nodes}
        node_ids.add("END")

        for edge in self.edges:
            if edge.from_node not in node_ids:
                raise ValueError(f"Edge starts from unknown node '{edge.from_node}'")
            if edge.to_node and edge.to_node not in node_ids:
                raise ValueError(f"Edge to unknown node '{edge.to_node}'")
            if edge.conditions:
                for cond in edge.conditions:
                    if cond.to not in node_ids:
                        raise ValueError(f"Conditional edge branch lead to unknown node '{cond.to}'")
            if edge.map:
                for target_node in edge.map.values():
                    if target_node not in node_ids:
                        raise ValueError(f"Router map target '{target_node}' is an unknown node")
            if edge.default and edge.default not in node_ids:
                raise ValueError(f"Default edge target '{edge.default}' is an unknown node")
        return self


# Backward-compatible alias used by legacy tests
AgentConfig = AgentGraphConfig


# ---------------------------------------------------------------------------
# Engine Execution Results (from engine.py)
# ---------------------------------------------------------------------------

class NodeOutcome(DynamicBaseModel):
    """Structured outcome of a node execution."""
    status: str = "success"
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineResult(DynamicBaseModel):
    """Structured result from AgentEngine.run_node() and internal execution methods."""
    messages: list[Any] = Field(default_factory=list)
    tool_history: list[str] = Field(default_factory=list)
    blackboard: BlackboardState | None = None
    is_truncated: bool = False
    signal: Any | None = None
    routing_target: str | None = None
    outcome: NodeOutcome | None = None


# ---------------------------------------------------------------------------
# Error Handling (from error_handler.py)
# ---------------------------------------------------------------------------

class ErrorClassification(BaseModel):
    """Structured error classification result."""
    error_type: str
    status_code: Optional[int] = None
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
# Task Persistence (from tasks.py)
# ---------------------------------------------------------------------------

class PersistMessagePayload(BaseModel):
    """Structured payload for message persistence tasks."""
    thread_id: str
    project_id: int
    role: str
    content: str
    thinking: str | None = None
    sequence_number: int = 0
    run_id: str | None = None
    status: str = "completed"
    parent_id: int | None = None
    tool_calls: list | None = None
    references: list[dict] | None = None
    action_type: str = "text"


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
    blackboard: BlackboardState
    structured_plan: str | dict | None = None
