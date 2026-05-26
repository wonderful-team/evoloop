from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
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
