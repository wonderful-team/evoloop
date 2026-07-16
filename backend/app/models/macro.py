"""Macro SQLModel — deterministic YAML scripts, independent from learned_skills.

Macros are whole-replay scripts executed by MacroService.run(); the LLM never
reads their content. Two provenance kinds coexist:
  - app_map_id set:    produced by the template factory from an AppMap
  - app_map_id NULL:   sedimented by the flywheel (never obsoleted by re-survey)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class Macro(Base):
    __tablename__ = "macros"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Provenance
    app_map_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    entity: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)

    # Definition
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text)
    trigger_patterns: Mapped[list[str]] = mapped_column(JSON)
    parameters: Mapped[list[dict]] = mapped_column(JSON)
    macro_script: Mapped[str] = mapped_column(Text)
    risk_tier: Mapped[str] = mapped_column(String(10), default="ui")
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_self_healing: Mapped[bool] = mapped_column(Boolean, default=True)

    # Lifecycle: pending_review | verified | obsolete
    status: Mapped[str] = mapped_column(
        String(20), default="pending_review", index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    namespace: Mapped[str | None] = mapped_column(
        String(500), nullable=True, index=True
    )

    # Pairing & tracing
    fallback_skill_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_map_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    member_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    def is_routable(self) -> bool:
        return self.is_active and self.status == "verified"
