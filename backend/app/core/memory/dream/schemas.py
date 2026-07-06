"""
Schemas for Deep Dream distillation.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DreamInsight:
    """A single distilled insight extracted from episode replay."""
    title: str
    content: str
    category: str  # "pattern" | "gotcha" | "decision" | "technique"
    utility_score: float = 0.8
    related_goals: list[str] = field(default_factory=list)


@dataclass
class DreamResult:
    """Result of a single dream cycle."""
    started_at: datetime
    finished_at: datetime | None = None
    episodes_replayed: int = 0
    insights_generated: list[DreamInsight] = field(default_factory=list)
    insight_ids: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.finished_at is not None

    @property
    def duration_seconds(self) -> float:
        end = self.finished_at or datetime.now()
        return (end - self.started_at).total_seconds()


@dataclass
class DreamRecord:
    """Persistent record of a dream cycle (for audit/status)."""
    id: str
    started_at: str
    finished_at: str | None = None
    episodes_count: int = 0
    insights_count: int = 0
    insight_ids: list[str] = field(default_factory=list)
    error: str | None = None
