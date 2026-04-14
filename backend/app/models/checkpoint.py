"""
Checkpoint Models
=================

User-initiated file snapshots for easy rollback.
Complements the automatic FileOperation system.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index, LargeBinary, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow

if TYPE_CHECKING:
    pass


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(Text, primary_key=True)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(Text)
    checkpoint: Mapped[dict] = mapped_column(JSON)
    checkpoint_metadata: Mapped[dict] = mapped_column("metadata", JSON, default={})


class CheckpointWrite(Base):
    __tablename__ = "checkpoint_writes"

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)
    blob: Mapped[bytes] = mapped_column(LargeBinary)
    task_path: Mapped[str] = mapped_column(Text, default="")


class CheckpointBlob(Base):
    __tablename__ = "checkpoint_blobs"

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    channel: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)


class CheckpointMigration(Base):
    __tablename__ = "checkpoint_migrations"

    v: Mapped[int] = mapped_column(Integer, primary_key=True)


class FileCheckpoint(Base):
    """
    A user-created snapshot of multiple files at a specific point in time.
    
    Unlike FileOperation (which tracks individual changes automatically),
    FileCheckpoint represents a named "milestone" that the user can roll back to.
    
    Note: Named FileCheckpoint to distinguish from LangGraph's Checkpoint model.
    """
    
    __tablename__ = "file_checkpoints"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # User-defined identifier
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Context
    thread_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    
    # Creation info
    created_by: Mapped[str] = mapped_column(String(20), default="manual")  # "manual" | "auto"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    
    # Optional: link to the message that triggered auto-creation
    source_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Relationships
    files: Mapped[list["FileCheckpointSnapshot"]] = relationship(
        "FileCheckpointSnapshot",
        back_populates="checkpoint",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    __table_args__ = (
        # Index for listing checkpoints in a thread
        Index('ix_file_checkpoints_thread_created', 'thread_id', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<FileCheckpoint(id={self.id}, name='{self.name}', files={len(self.files)})>"


class FileCheckpointSnapshot(Base):
    """
    A single file snapshot within a FileCheckpoint.
    Stores the complete file content (not a diff) for reliable restoration.
    """
    
    __tablename__ = "file_checkpoint_snapshots"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Foreign key
    checkpoint_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("file_checkpoints.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # File info
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # Complete content
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256
    
    # Metadata
    file_size: Mapped[int] = mapped_column(Integer, default=0)  # Bytes
    line_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    checkpoint: Mapped["FileCheckpoint"] = relationship("FileCheckpoint", back_populates="files")
    
    __table_args__ = (
        # Ensure unique file per checkpoint
        Index('ix_file_checkpoint_snapshots_unique', 'checkpoint_id', 'file_path', unique=True),
    )
    
    def __repr__(self) -> str:
        return f"<FileCheckpointSnapshot(checkpoint_id={self.checkpoint_id}, path='{self.file_path[:50]}...')>"
