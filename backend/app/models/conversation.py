from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    member_id: Mapped[int] = mapped_column(Integer, default=0, index=True)  # Owner member ID
    project_id: Mapped[int | None] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(50))  # "human", "ai"
    content: Mapped[str] = mapped_column(Text)
    meta_data: Mapped[dict | None] = mapped_column(JSON, nullable=True) # Silent audit & state metadata
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)  # Raw reasoning content string
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=utcnow, nullable=True)
    sequence_number: Mapped[int | None] = mapped_column(Integer)  # Thread-local ordering

    # Optional: reference to checkpoint ID if we want to linked back to graph state
    checkpoint_id: Mapped[str | None] = mapped_column(String(255))

    # Tool calls storage (for AI messages that trigger tools)
    tool_calls: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

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
    status: Mapped[str | None] = mapped_column(String(50))  # pending, streaming, running, completed, failed, cancelled, waiting_human

    # Threading support for message branching
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True)

    # Tool execution attribution
    tool_call_id: Mapped[str | None] = mapped_column(String(255), index=True)
    tool_name: Mapped[str | None] = mapped_column(String(255)) # Tool name or user name

    parent: Mapped["Message | None"] = relationship("Message", remote_side="[Message.id]", backref="children")

    # Message source — identifies which client/entry produced this message
    # values: "desktop", "mobile", "api"
    source: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # Device Identification for A2A Attribution
    executor_device_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    executor_device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Cloud Sync State
    # values: 'pending', 'synced', 'failed'
    sync_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Remember state: extracted concept for long-term memory recall
    is_remembered: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)
    remembered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    memory_concept_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    references: Mapped[list["MessageReference"]] = relationship(back_populates="message", cascade="all, delete-orphan")

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages",
        primaryjoin="Message.thread_id == Conversation.id",
        foreign_keys=[thread_id],
    )


class MessageReference(Base):
    """
    Persistent Context References
    挂载在消息上的所有非文本引用的持久化存储。

    type 字段的合法值（与 engine/message/schemas.MessageReference.type 严格对应）：
    - "file"       : 可下载文件（PDF、Excel、TXT 等）
    - "image"      : 图片（截图、AI 生成图）
    - "audio"      : 音频（语音回复、上传音频）
    - "video"      : 视频（上传或生成视频）
    - "message"    : 引用历史消息（target_id = message UUID）
    - "artifact"   : 可交互组件（echarts/mermaid/map/html）
    - "changeset"  : 代码变更集（target_id = run_id，meta_data 含 files 列表）
    - "skill"      : 技能引用（target_id = skill_id）
    - "directory"  : 目录引用（target_id = 目录路径，meta_data 含相关目录元数据）
    """

    __tablename__ = "message_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    message_id: Mapped[str] = mapped_column(String(255), ForeignKey("messages.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))  # 见 docstring 中的合法值列表
    target_id: Mapped[str] = mapped_column(String(255))  # 资源路径、消息 ID、URL 或唯一标识
    target_name: Mapped[str] = mapped_column(String(255))  # 人类可读名称
    meta_data: Mapped[dict | None] = mapped_column(JSON, default=None)  # 扩展元数据（size, mime_type, files, artifact_type 等）
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    message: Mapped["Message"] = relationship(back_populates="references")


class Conversation(Base):
    """
    Metadata for a conversation thread.
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # thread_id (uuid)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    member_id: Mapped[int] = mapped_column(Integer, default=0, index=True)  # Owner member ID
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Cloud Sync State
    # values: 'pending', 'synced', 'failed'
    sync_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Pin State
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)

    # Thread Tree Relationships for A2A
    root_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    parent_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Device Identification for A2A Attribution
    caller_device_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    executor_device_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    executor_device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        primaryjoin=lambda: Message.thread_id == Conversation.id,
        foreign_keys=[Message.thread_id],
    )
    plan: Mapped["Plan | None"] = relationship(
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

    thread_id: Mapped[str] = mapped_column(String(255), primary_key=True, autoincrement=False)
    status: Mapped[str] = mapped_column(String(50), default="idle")
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    main_goal: Mapped[str] = mapped_column(Text, default="")
    artifacts_json: Mapped[str] = mapped_column(Text, default="[]")
    agent_state_json: Mapped[str] = mapped_column(Text, default="{}")
    active_memories_json: Mapped[str] = mapped_column(Text, default="[]")
    human_request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_outcome: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    macro_creation_eligible: Mapped[bool] = mapped_column(default=False)
    # React 引擎度量埋点（§10.2.1 / 阶段 D）：每 run 汇总
    llm_calls: Mapped[int] = mapped_column(default=0)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    tool_errors: Mapped[int] = mapped_column(default=0)
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
    # 授权门控的机器可读资源锚点（拒绝判死 / 近期放行查询的数据源）。
    # 终态约定：路径判断只允许查这两列（归一化绝对路径），
    # 禁止再对 description 文本做 contains/endswith 之类的子串匹配。
    resource_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    resource_action: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # 判死/授权的自然过期时间（如拒绝 TTL 到期后允许再次发起审批）。
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
