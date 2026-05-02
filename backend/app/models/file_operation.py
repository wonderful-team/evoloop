from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class FileOperation(Base):
    """
    Tracks formal file-system modifications performed by an Agent.
    Used for generating Changeset Trees, Diff views, and physical Undo.
    """

    __tablename__ = "file_operations"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)

    # Associate with a specific message or run for traceability
    message_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    file_path: Mapped[str] = mapped_column(Text)
    operation: Mapped[str] = mapped_column(String(20))  # "ADD", "EDIT", "DELETE"

    # Stores unified diff for EDIT, or full content for ADD
    diff_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Original file content before modification (for Undo/Revert)
    # - ADD: None (file did not exist)
    # - EDIT: Previous content before edit
    # - DELETE: Full content of deleted file
    original_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
