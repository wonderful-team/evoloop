import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class TodoStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TodoItem(Base):
    __tablename__ = "todos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TodoStatus] = mapped_column(Enum(TodoStatus), default=TodoStatus.PENDING)
    priority: Mapped[TodoPriority] = mapped_column(Enum(TodoPriority), default=TodoPriority.MEDIUM)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_conversation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    # Project Context
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
