"""
Citation tracking models — unified under the main relational database.

Previously stored in a separate citations.db SQLite file.
Now lives in the main database (SQLite or PostgreSQL) alongside other app data.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class CitationEvent(Base):
    """A single citation event (Agent referencing a document)."""

    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(1024), index=True)
    doc_path: Mapped[str] = mapped_column(String(1024))
    tool_used: Mapped[str] = mapped_column(String(50))
    session_id: Mapped[str | None] = mapped_column(String(255), index=True)
    agent_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class DocStat(Base):
    """Materialized citation statistics for a document."""

    __tablename__ = "doc_stats"

    doc_id: Mapped[str] = mapped_column(String(1024), primary_key=True)
    doc_path: Mapped[str] = mapped_column(String(1024))
    total_citations: Mapped[int] = mapped_column(Integer, default=0)
    unique_sessions: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tools_used: Mapped[str | None] = mapped_column(Text)  # JSON dict
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SessionDoc(Base):
    """Session-document pairs for finding related (co-cited) documents."""

    __tablename__ = "session_docs"

    session_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(1024), primary_key=True)
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
