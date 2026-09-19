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
    # Queue lifecycle: proposed, pending, in_progress, self_checked,
    # waiting_acceptance, completed, failed, cancelled
    status: Mapped[str] = mapped_column(String(50), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100

    # ---- Queue fields (autonomous task loop, stage 1) ----
    # Full executable instruction for the agent (first-class column: editable
    # from the board UI and by the agent tool; JSON task_data stays for the rest)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Task kind: "once" (default) or "recurring" (trigger_spec drives requeue)
    type: Mapped[str] = mapped_column(String(20), default="once")
    # Entry source of the task row: user / external / agent (creator semantics)
    source: Mapped[str] = mapped_column(String(20), default="user", index=True)
    # Derivation path: {kind: message|patrol_run|agent_run|event, ref: ...}
    source_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Idempotency key for external events: "{source}:{event_id}"
    dedup_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    # Acceptance tier inherited from MCP risk annotations: T1-T4
    risk_level: Mapped[str | None] = mapped_column(String(4), nullable=True)
    # Due time for one-shot tasks (scheduling scan key)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Recurring spec (cron or "interval:seconds"); non-null = recurring task
    trigger_spec: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Next run for recurring tasks (advanced on claim to prevent re-dispatch)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Structured self-check report: {verdict, checks, deviations}
    self_check: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Acceptance receipt: {by, at, verdict, feedback}
    acceptance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Latest workspace thread for board drill-down
    last_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Human-readable short number assigned at creation: "#T-<n>" per project
    task_no: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Origin conversation thread (dialogue where the task was created); the
    # reviewer runs here after completion. Null = board/external task (no review).
    origin_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Times the reviewer rejected the result (cap 2 → failed, human arbitration)
    review_count: Mapped[int] = mapped_column(Integer, default=0)


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
