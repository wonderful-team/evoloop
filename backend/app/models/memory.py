from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class MemoryConcept(Base):
    __tablename__ = "memory_concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    member_id: Mapped[int] = mapped_column(Integer, default=0, index=True)  # Owner member ID
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    related_files: Mapped[list[str] | None] = mapped_column(JSON)  # List of file paths
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MemoryIndex(Base):
    __tablename__ = "memory_index"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(50), nullable=False)
    privacy: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    member_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Traceability 元数据追溯字段
    source_file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    source_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    source_run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    source_wiki_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    content_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    utility_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

