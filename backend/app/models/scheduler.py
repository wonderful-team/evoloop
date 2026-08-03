from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class AutonomousTask(Base):
    """
    Represents a periodic or intent-driven task managed by the Agent.

    Instead of simple cron jobs, these are high-level 'delegations' from the user
    to the agent, allowing for autonomous execution, failure analysis, and self-healing.
    """

    __tablename__ = "autonomous_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Intent Context
    intent_description: Mapped[str] = mapped_column(Text)  # High-level goal (e.g. "Monitor iPhone 15 prices daily")
    project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # Owner member ID for multi-user isolation
    member_id: Mapped[int] = mapped_column(Integer, default=0, index=True)

    # Execution Blueprint
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("learned_skills.id"), index=True)
    params_template: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # Template with placeholders

    # Trigger Configuration
    trigger_type: Mapped[str] = mapped_column(String(50), default="cron")  # "cron", "event", "interval"
    trigger_spec: Mapped[str] = mapped_column(String(255))  # e.g. "0 12 * * *" or "interval:3600"

    # Status & Health
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    # Lifecycle Timestamps
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Dead Letter Info
    last_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_dead_letter: Mapped[bool] = mapped_column(Boolean, default=False)  # True if task is moved to DLQ due to repeated failures
