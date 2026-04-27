from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow
from .planning import Plan


class ThreadSequence(Base):
    """
    Atomic sequence counter per thread for message ordering.
    Replaces SELECT MAX(sequence_number) + 1 to prevent race conditions.
    """

    __tablename__ = "thread_sequences"

    thread_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    next_seq: Mapped[int] = mapped_column(Integer, default=1)


class Message(Base):
    """
    Flattened message log for full-text search.
    Populated asynchronously when messages are generated.
    """

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "sequence_number", name="uq_message_thread_seq"),
        Index("ix_messages_thread_visible_id", "thread_id", "is_visible", "id"),
        # NOTE: For PostgreSQL deployments, a GIN index on content would help
        # full-text search. SQLite (embedded mode) does not support GIN;
        # consider FTS5 virtual table for large local message volumes.
        Index("ix_messages_content", "content"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(50))  # "human", "ai"
    content: Mapped[str] = mapped_column(Text)
    thinking: Mapped[str | None] = mapped_column(Text)  # Separate reasoning content
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=utcnow, nullable=True)
    sequence_number: Mapped[int | None] = mapped_column(Integer)  # Thread-local ordering

    # Optional: reference to checkpoint ID if we want to linked back to graph state
    checkpoint_id: Mapped[str | None] = mapped_column(String(255))

    # Tool calls storage (for AI messages that trigger tools)
    tool_calls: Mapped[list[dict] | None] = mapped_column(JSON)

    # Action Type Discriminator
    # values: 'text' (default), 'tool_output', 'thinking', 'system'
    action_type: Mapped[str] = mapped_column(String(50), default="text", server_default="text")

    # Message Category for unified lifecycle management
    # values: 'user', 'assistant_response', 'assistant_tool_call', 'tool_output',
    #         'internal_tool_call', 'internal_reasoning', 'internal_system', 'internal_llm_json'
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Content type for rendering differentiation
    # values: 'text', 'markdown', 'json', 'multipart'
    content_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Visibility flag for pagination (hide intermediate tool-calling AI/Tool messages)
    is_visible: Mapped[bool] = mapped_column(default=True, server_default="1")

    # Message-Run Association for tracking execution context
    run_id: Mapped[str | None] = mapped_column(String(255), index=True)  # Associate with a specific execution run
    status: Mapped[str | None] = mapped_column(String(50))  # pending, streaming, completed, failed, waiting_human

    # Threading support for message branching
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    
    # Tool execution attribution
    tool_call_id: Mapped[str | None] = mapped_column(String(255), index=True)
    tool_name: Mapped[str | None] = mapped_column(String(255)) # Tool name or user name
    
    parent: Mapped[Optional["Message"]] = relationship("Message", remote_side="[Message.id]", backref="children")

    # Cloud Sync State
    # values: 'pending', 'synced', 'failed'
    sync_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    references: Mapped[list["MessageReference"]] = relationship(back_populates="message", cascade="all, delete-orphan")

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
        primaryjoin="Message.thread_id == Conversation.id",
        foreign_keys=[thread_id],
    )


class MessageReference(Base):
    """
    Persistent Context References
    Tracks what memory/knowledge/tool was used to generate a message.
    """

    __tablename__ = "message_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))  # memory, tool, knowledge, file, audio, image
    target_id: Mapped[str] = mapped_column(String(255))  # ID or Name of the item (URL for audio/images)
    target_name: Mapped[str] = mapped_column(String(255))  # Human readable name
    meta_data: Mapped[dict | None] = mapped_column(JSON, default=None)  # Additional metadata (duration, transcript, etc.)
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

    # Cloud Sync State
    # values: 'pending', 'synced', 'failed'
    sync_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        primaryjoin=lambda: Message.thread_id == Conversation.id,
        foreign_keys=[Message.thread_id],
    )
    plan: Mapped[Optional["Plan"]] = relationship(
        "Plan",
        back_populates="conversation",
        uselist=False,
        cascade="all, delete-orphan",
    )


class AgentActivity(Base):
    """
    Stores agent execution activity state for real-time UI tracking.
    Replaces FileCache-based activity storage for better performance and reliability.
    """

    __tablename__ = "agent_activities"

    thread_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), default="idle")
    main_goal: Mapped[str] = mapped_column(Text, default="")
    steps_json: Mapped[str] = mapped_column(Text, default="[]")
    artifacts_json: Mapped[str] = mapped_column(Text, default="[]")
    agent_state_json: Mapped[str] = mapped_column(Text, default="{}")
    active_memories_json: Mapped[str] = mapped_column(Text, default="[]")
    human_request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_outcome: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class HumanRequest(Base):
    """
    Stores pending human interactions (HITL - Human In The Loop)
    """

    __tablename__ = "human_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    thread_id: Mapped[str] = mapped_column(String(36), index=True)  # Not FK to avoid strict dependency
    type: Mapped[str] = mapped_column(String(50))  # 'text', 'choice', 'confirmation', 'approval'
    description: Mapped[str] = mapped_column(Text)  # Prompt/Question
    options: Mapped[list[str] | None] = mapped_column(JSON)  # List of choices
    context: Mapped[str | None] = mapped_column(Text)  # Additional context
    default_value: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, completed, cancelled, timeout
    result: Mapped[str | None] = mapped_column(Text)  # JSON string of user response
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
