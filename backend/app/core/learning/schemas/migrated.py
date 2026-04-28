"""Schemas for learning module."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.infrastructure.pydantic_base import DynamicBaseModel


class ActionSource(str, Enum):
    """Who initiated the action."""
    AGENT = "agent"
    HUMAN = "human"


class ActionCategory(str, Enum):
    """High-level categorization of actions."""
    NAVIGATION = "navigation"  # File/URL navigation
    EDIT = "edit"  # Content modification
    QUERY = "query"  # Information retrieval
    COMMAND = "command"  # System command execution
    INTERACTION = "interaction"  # UI interaction
    DECISION = "decision"  # Approval/choice
    SYSTEM_INTERACTION = "system_interaction"  # Global system interaction
    OTHER = "other"

class SkillParams(DynamicBaseModel):
    """Dynamic parameters extracted during skill matching."""

class SkillListItem(DynamicBaseModel):
    """Lightweight item for active skills list."""
    id: int
    name: str
    namespace: str = "general"
    description: str = ""

class SkillMatch(DynamicBaseModel):
    """Result of skill matching (intentional execution)."""
    skill_id: int
    skill_name: str
    confidence: float
    reasoning: str
    extracted_params: SkillParams = Field(default_factory=SkillParams)

class CompressionConfig(DynamicBaseModel):
    """压缩配置"""
    max_width: int
    quality: int                  # JPEG 质量 0-100
    detail_level: str             # "low" or "high" (for LLM)
    format: str = "JPEG"

class CompressedFrame(DynamicBaseModel):
    """压缩后的帧数据"""
    data: bytes                   # JPEG 数据
    width: int
    height: int
    original_size: tuple[int, int]  # 原始分辨率
    compression_ratio: float      # 压缩比
    detail_level: str             # "low" or "high"

    # 动态注入的语义信息
    timestamp: float | None = None
    description: str | None = None
    norm_events: list[dict[str, Any]] = Field(default_factory=list)

class NormalizedEvent(DynamicBaseModel):
    """归一化后的事件"""
    action: str
    norm_x: float | None = Field(None, ge=0.0, le=1.0)       # 0.0-1.0
    norm_y: float | None = Field(None, ge=0.0, le=1.0)
    target_text: str | None = None
    timestamp: float
    description: str              # 人类可读描述

class KeyframeCandidate(DynamicBaseModel):
    """关键帧候选"""
    timestamp: float
    context: str           # "pre_action", "post_action", "transition"
    description: str
    related_event: Any
    priority: int          # 3=high, 2=medium, 1=low

    def __repr__(self):
        return f"Keyframe({self.timestamp:.2f}s, {self.context}, P{self.priority})"

class RecordingSession(DynamicBaseModel):
    """录制会话数据"""
    video_path: str
    session_id: str
    task_description: str
    thread_id: str | None = None

class VideoInfo(DynamicBaseModel):
    """视频元信息"""
    duration: float
    width: int
    height: int
    fps: float

class ActionRegistryItem(DynamicBaseModel):
    """Action metadata injected into prompt templates."""
    id: str
    description: str
    params: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)

class SkillImportResult(DynamicBaseModel):
    """Result of a bulk skill import operation."""
    total_found: int = 0
    imported: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)

class ValidationMetadata(DynamicBaseModel):
    """Dynamic metadata from skill validation."""

class ValidationResult(BaseModel):
    is_valid: bool
    status: str  # "healthy", "warning", "error"
    errors: list[str] = []
    warnings: list[str] = []
    metadata: ValidationMetadata | None = None

class SynthesizedSopConfig(DynamicBaseModel):
    """Result of smart synthesis: a Phase 4 graph configuration."""
    name: str = "synthesized_sop"
    version: str = "1.0"
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)

class TraceAction(DynamicBaseModel):
    """A single action extracted from a trace."""
    action: str
    target: str | None = None
    params: dict = Field(default_factory=dict)

class MacroVerificationResult(DynamicBaseModel):
    status: str
    success: bool
    missing_keys: list[str] = []
    extracted_count: int = 0
    error: str | None = None

class UIContext(DynamicBaseModel):
    """Visual/UI context at the time of action."""
    screenshot_path: str | None = None
    element_selector: str | None = None
    element_text: str | None = None

class TraceActionArgs(DynamicBaseModel):
    """Dynamic arguments for a trace action."""

class TraceStateContext(DynamicBaseModel):
    """Dynamic state context for a trace step."""
    app_name: str | None = None
    is_mirrored: bool | None = None
    window_title: str | None = None

class TraceSummary(DynamicBaseModel):
    """Summary of a trace sequence."""
    thread_id: str
    task_name: str | None = None
    total_steps: int
    human_steps: int
    agent_steps: int
    tools_used: list[str] = Field(default_factory=list)
    success: bool = True

class TraceStep(DynamicBaseModel):
    """
    A single semantic step in a trace sequence.
    Represents one complete action-observation pair.
    """
    step_number: int
    source: ActionSource
    category: ActionCategory

    # Core action info
    action_type: str  # Raw type (tool_call, click, input, etc.)
    action_name: str  # Semantic name (e.g., "read_file", "click_button")
    action_args: TraceActionArgs = Field(default_factory=TraceActionArgs)

    # Observation/result
    observation: str | None = None
    success: bool = True

    # Context
    node_name: str = "unknown"
    state_context: TraceStateContext = Field(default_factory=TraceStateContext)
    ui_context: UIContext | None = None

    # Metadata
    timestamp: float | None = None
    user_feedback: str | None = None

class TraceParameters(DynamicBaseModel):
    """Dynamic parameters for a recorded action."""

class TraceContext(DynamicBaseModel):
    """Dynamic context (view hierarchy, URL, etc.) for a recorded action."""

class ActionTrace(DynamicBaseModel):
    """Represents a single user action captured during demonstration."""
    timestamp: float
    action_type: str  # click, type, swipe, key, navigate, etc.
    platform: str     # android, web, desktop
    parameters: TraceParameters
    context: TraceContext = Field(default_factory=TraceContext) # View hierarchy, URL, etc.
    screenshot_path: str | None = None
