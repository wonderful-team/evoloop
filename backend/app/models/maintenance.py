"""
Maintenance report models — unified under the main relational database.

Previously stored in search.db (SQLite FTS5 database).
Now lives in the main database (SQLite or PostgreSQL) alongside other app data.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class MaintenanceReport(Base):
    """A maintenance run report (auto-maintenance / knowledge base cleanup)."""

    __tablename__ = "maintenance_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    level: Mapped[str | None] = mapped_column(String(50))
    dry_run: Mapped[bool | None] = mapped_column(Boolean, default=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    summary_json: Mapped[str | None] = mapped_column(Text)
    report_json: Mapped[str | None] = mapped_column(Text)
