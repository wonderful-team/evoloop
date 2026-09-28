"""Schemas for learning module."""

from enum import Enum

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
    project_id: int | None = None


class SkillMatch(DynamicBaseModel):
    """Result of skill matching (intentional execution)."""

    skill_id: int
    skill_name: str
    confidence: float
    reasoning: str
    extracted_params: SkillParams = Field(default_factory=SkillParams)


class RecordingSession(DynamicBaseModel):
    """录制会话数据"""

    video_path: str
    session_id: str
    task_description: str
    thread_id: str | None = None


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


class UIContext(DynamicBaseModel):
    """Visual/UI context at the time of action."""

    screenshot_path: str | None = None
    element_selector: str | None = None
    element_text: str | None = None


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


class TraceActionArgs(DynamicBaseModel):
    """Dynamic arguments for a trace action."""


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
    platform: str  # android, web, desktop
    parameters: TraceParameters
    context: TraceContext = Field(
        default_factory=TraceContext
    )  # View hierarchy, URL, etc.
    screenshot_path: str | None = None
