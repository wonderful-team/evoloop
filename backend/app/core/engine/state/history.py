from datetime import datetime
from typing import Any
from pydantic import Field
from app.infrastructure.pydantic_base import DynamicBaseModel


class ToolCall(DynamicBaseModel):
    """Structured representation of a tool call from an AIMessage."""
    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolStep(DynamicBaseModel):
    """
    Standard model for a single tool execution step within an AI message.
    Used for both persistent history and real-time streaming.
    """
    id: str
    tool: str  # Original tool identifier (e.g., "search_web")
    tool_name: str | None = None  # Friendly name for display (e.g., "搜索网页")
    input: dict | str | Any = Field(default_factory=dict)
    output: str = ""
    status: str = "success"  # success, error, pending
    duration: float | None = None
    tool_call_id: str | None = None


class FoldedMessage(DynamicBaseModel):
    """
    Base model for messages in a folded format where tool outputs 
    are nested inside their parent AI message.
    """
    id: str
    role: str  # human, ai, system, tool
    content: str = ""
    thinking: str | None = None
    created_at: str | datetime | None = None
    steps: list[ToolStep] = Field(default_factory=list)
    tool_calls: list[dict] | None = None
    
    # Metadata for specific message types
    metadata: dict[str, Any] = Field(default_factory=dict)
