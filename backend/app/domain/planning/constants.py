"""Planning domain constants."""

from enum import Enum

RETRIEVAL_LIMIT = 5
"""Number of code snippets retrieved for feasibility analysis context."""

TREE_MAX_DEPTH = 3
"""Maximum depth of the project tree generated for feasibility analysis."""

TREE_FILE_LIMIT = 30
"""Maximum number of files included in the generated project tree."""


class PlanStatus(str, Enum):
    """High-level status of a ``Plan`` (active / completed / archived)."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class PlanStepStatus(str, Enum):
    """Status of an individual plan step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"

