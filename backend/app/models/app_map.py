"""AppMap SQLModel — one source-survey artifact per (project, entity)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.models.codebase import AppMapRouteLink


class AppMap(Base):
    """Structured source-level map of one entity in one project.

    Five-layer JSON payload (routes/actions/elements/db_tables/extra) produced
    by the AppMap-analysis Agent and consumed by the template factory.
    """

    __tablename__ = "app_maps"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    entity: Mapped[str] = mapped_column(String(100), index=True)
    platform: Mapped[str] = mapped_column(String(20), default="web")
    aliases: Mapped[list[str]] = mapped_column(JSON)

    # Five-layer structured data (JSON columns)
    routes: Mapped[list[dict]] = mapped_column(JSON)
    actions: Mapped[list[dict]] = mapped_column(JSON)
    elements: Mapped[list[dict]] = mapped_column(JSON)
    db_tables: Mapped[list[dict]] = mapped_column(JSON)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Versioning & provenance
    map_version: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str] = mapped_column(String(64))
    generation_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Lifecycle
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    validation_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    member_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    route_links: Mapped[list[AppMapRouteLink]] = relationship(
        "AppMapRouteLink", back_populates="app_map", cascade="all, delete-orphan"
    )
