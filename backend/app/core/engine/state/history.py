"""
Message history models for LangGraph state.

NOTE: ToolStep / FoldedMessage 的 canonical 定义在 app.core.engine.message.schemas
（ToolBlock / MessageBlock）。此文件保留运行时内部使用的轻量版本，API/SSE/Mobile
传输请使用 app.core.engine.message.schemas 中的标准化模型。
"""

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
    tool_name: str | None = None  # Generic friendly name (e.g., "搜索网页")

    input: dict | str | Any = Field(default_factory=dict)
    output: str = ""
    status: str = "success"  # success, error, pending
    duration: float | None = None
    tool_call_id: str | None = None
    tool_meta: dict[str, Any] | None = None

    @classmethod
    def model_validate(cls, obj: Any, **kwargs):
        """Normalize legacy snapshot formats before validation.
        
        Old format (written before schema stabilization):
          {'id': 1, 'name': 'Using ...', 'details': None, ...}
        Current format:
          {'id': 'uuid', 'tool': 'tool_name', 'output': '...', ...}
        """
        if isinstance(obj, dict):
            data = dict(obj)
            # Coerce int id → str
            if "id" in data and not isinstance(data["id"], str):
                data["id"] = str(data["id"])
            # Map legacy 'name' → 'tool' if 'tool' is absent
            if "tool" not in data and "name" in data:
                data["tool"] = data["name"]
            # Map legacy 'details' → 'output' if 'output' is absent
            if "output" not in data and "details" in data:
                data["output"] = str(data["details"] or "")
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)


class FoldedMessage(DynamicBaseModel):
    """
    Base model for messages in a folded format where tool outputs 
    are nested inside their parent AI message.
    """
    id: str | None = None
    role: str  # human, ai, system, tool
    content: str = ""
    thinking: list[dict[str, Any]] | None = None
    created_at: str | datetime | None = None
    steps: list[ToolStep] = Field(default_factory=list)
    tool_calls: list[dict] | None = None
    
    # Metadata for specific message types
    metadata: dict[str, Any] = Field(default_factory=dict)
