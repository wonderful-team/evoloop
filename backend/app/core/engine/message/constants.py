"""Message status vocabulary — centralized constants for the message domain."""

from enum import Enum


class MessageStatus(str, Enum):
    """Persisted/streamed message lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_HUMAN = "waiting_human"


class MessageRole(str, Enum):
    """Message role vocabulary persisted in the database."""

    HUMAN = "human"
    AI = "ai"
    TOOL = "tool"
    SYSTEM = "system"


class MessageContentType(str, Enum):
    """Message content representation format."""

    TEXT = "text"
    MARKDOWN = "markdown"
    JSON = "json"
    MULTIPART = "multipart"


class MessageActionType(str, Enum):
    """Message action type used for rendering and routing."""

    TEXT = "text"
    THINKING = "thinking"
    TOOL_OUTPUT = "tool_output"
