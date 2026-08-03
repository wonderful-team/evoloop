from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class ProjectTask(Base):
    """
    Universal Project Task - Independent of requirement analysis.
    Supports hierarchical subtasks and synchronization with EvoCloud.

    Sync status flow:
        pending → syncing → synced → failed

    Hierarchy:
        - parent_id is null: root task
        - parent_id is set: subtask of parent
    """

    __tablename__ = "project_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Optional link to requirement analysis (for historical compatibility or future trace)
    analysis_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    member_id: Mapped[int] = mapped_column(Integer, default=0, index=True)

    # EvoCloud task ID (backfilled after sync)
    evocloud_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Hierarchy support for subtasks
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("project_tasks.id"), nullable=True, index=True)

    # Task execution status
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, in_progress, completed, failed
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100

    # Task data (JSON)
    # {
    #   "title": "Task Title",
    #   "description": "Detailed description",
    #   "priority": "high|medium|low",
    #   "estimated_hours": 8,
    #   "category": "frontend|backend|database",
    #   "tags": [...],
    #   "acceptance_criteria": [...]
    # }
    task_data: Mapped[dict] = mapped_column(JSON, default=dict)

    # Sync status
    sync_status: Mapped[str] = mapped_column(String(50), default="pending")
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    # Relationships
    parent: Mapped["ProjectTask | None"] = relationship(
        "ProjectTask",
        remote_side="ProjectTask.id",
        back_populates="subtasks"
    )
    subtasks: Mapped[list["ProjectTask"]] = relationship(
        "ProjectTask",
        back_populates="parent",
        cascade="all, delete-orphan"
    )
