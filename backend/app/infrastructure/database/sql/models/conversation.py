from datetime import datetime
from typing import ForwardRef, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow

# Use ForwardRef for deferred resolution to avoid circular imports with 'planning.py'
Plan = ForwardRef("Plan")


class Message(Base):
    """
    Flattened message log for full-text search.
    Populated asynchronously when messages are generated.
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(50))  # "human", "ai"
    content: Mapped[str] = mapped_column(Text)
    thinking: Mapped[str | None] = mapped_column(Text)  # Separate reasoning content
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sequence_number: Mapped[int | None] = mapped_column(Integer)  # Thread-local ordering

    # Optional: reference to checkpoint ID if we want to linked back to graph state
    checkpoint_id: Mapped[str | None] = mapped_column(String(255))

    # New columns for tool calls
    tool_calls: Mapped[list[dict] | None] = mapped_column(JSON)
    tool_output: Mapped[str | None] = mapped_column(Text)

    # Phase 3: Message-Run Association
    run_id: Mapped[str | None] = mapped_column(String(255), index=True)  # Associate with a specific execution run
    status: Mapped[str | None] = mapped_column(String(50))  # pending, streaming, completed, failed, waiting_human
    steps_snapshot: Mapped[list[dict] | None] = mapped_column(JSON)  # Embedded task steps at completion

    # Phase 4: Threading
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    parent: Mapped[Optional["Message"]] = relationship("Message", remote_side="[Message.id]", backref="children")

    references: Mapped[list["MessageReference"]] = relationship(back_populates="message", cascade="all, delete-orphan")

    conversation: Mapped["Conversation"] = relationship(back_populates="messages",
                                                        primaryjoin="Message.thread_id == Conversation.id",
                                                        foreign_keys=[thread_id])


class MessageReference(Base):
    """
    Phase 9: Persistent Context References
    Tracks what memory/knowledge/tool was used to generate a message.
    """
    __tablename__ = "message_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))  # memory, tool, knowledge, file
    target_id: Mapped[str] = mapped_column(String(255))  # ID or Name of the item
    target_name: Mapped[str] = mapped_column(String(255))  # Human readable name
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    message: Mapped["Message"] = relationship(back_populates="references")


class Conversation(Base):
    """
    Metadata for a conversation thread.
    """
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # thread_id (uuid)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan",
                                                     primaryjoin=lambda: Message.thread_id == Conversation.id,
                                                     foreign_keys=[Message.thread_id])
    plan: Mapped[Optional["Plan"]] = relationship("Plan", back_populates="conversation", uselist=False,
                                                  cascade="all, delete-orphan")


class HumanRequest(Base):
    """
    Stores pending human interactions (Phase 0.2)
    """
    __tablename__ = "human_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    thread_id: Mapped[str] = mapped_column(String(36), index=True)  # Not FK to avoid strict dependency
    type: Mapped[str] = mapped_column(String(50))  # 'input', 'confirmation', 'selection'
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, completed, rejected
    result: Mapped[str | None] = mapped_column(Text)  # JSON string of user input
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
