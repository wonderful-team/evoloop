"""Planning domain constants."""

from enum import Enum


class PlanStatus(str, Enum):
    """High-level status of a ``Plan`` (active / completed)."""

    ACTIVE = "active"
    COMPLETED = "completed"


class PlanStepStatus(str, Enum):
    """Status of an individual plan step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"
