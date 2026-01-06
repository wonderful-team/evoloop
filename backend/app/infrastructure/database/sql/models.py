from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text, Boolean, JSON, Float, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


# Project table removed. Projects are now managed externally via ImagicBox.

class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    # project_id is now a loose reference to the external project ID
    # We index it for faster lookups, but DO NOT enforce foreign key constraint to a local table
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024))
    local_path: Mapped[Optional[str]] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    files: Mapped[List["SourceFile"]] = relationship(back_populates="repository", cascade="all, delete-orphan")


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"))
    path: Mapped[str] = mapped_column(String(1024), index=True)  # Relative path in repo
    checksum: Mapped[str] = mapped_column(String(64))  # SHA256 or similar
    last_indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    repository: Mapped["Repository"] = relationship(back_populates="files")
    chunks: Mapped[List["CodeChunk"]] = relationship(back_populates="source_file", cascade="all, delete-orphan")
    entities: Mapped[List["CodeEntity"]] = relationship(back_populates="file", cascade="all, delete-orphan")


class CodeEntity(Base):
    __tablename__ = "code_entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"))

    name: Mapped[str] = mapped_column(String(255), index=True)
    type: Mapped[str] = mapped_column(String(50))  # class, function, variable
    full_name: Mapped[str] = mapped_column(String(512), index=True)  # FQN, e.g. module.Class.method

    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)

    # Optional metadata (complexity, docstring summary, etc.) could go here

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    file: Mapped["SourceFile"] = relationship(back_populates="entities")
    
    # Relationships
    relations_from: Mapped[List["CodeRelation"]] = relationship("CodeRelation", foreign_keys="CodeRelation.source_entity_id", back_populates="source_entity", cascade="all, delete-orphan")
    relations_to: Mapped[List["CodeRelation"]] = relationship("CodeRelation", foreign_keys="CodeRelation.target_entity_id", back_populates="target_entity", cascade="all, delete-orphan")


class CodeRelation(Base):
    __tablename__ = "code_relations"

    id: Mapped[int] = mapped_column(primary_key=True)

    source_entity_id: Mapped[int] = mapped_column(ForeignKey("code_entities.id"))
    target_entity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("code_entities.id"), nullable=True)
    target_name: Mapped[Optional[str]] = mapped_column(String(512), index=True) # Unresolved target name

    relation_type: Mapped[str] = mapped_column(String(50))  # calls, inherits, imports, defines

    # Optional: properties like confidence or count

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source_entity: Mapped["CodeEntity"] = relationship("CodeEntity", foreign_keys=[source_entity_id], back_populates="relations_from")
    target_entity: Mapped[Optional["CodeEntity"]] = relationship("CodeEntity", foreign_keys=[target_entity_id], back_populates="relations_to")


class CodeChunk(Base):
    """
    Represents a chunk of code (e.g., a function, class, or block) that is vectorized.
    """
    __tablename__ = "code_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"), index=True)

    # Chunk Metadata
    chunk_type: Mapped[str] = mapped_column(String(50))  # e.g. "function", "class", "module"
    identifier: Mapped[str] = mapped_column(String(255))  # e.g. "MyClass.my_method"
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)

    # Vector Embedding (1536 dims for OpenAI, 768 for others - make it generic or config dependent?)
    # Using 1536 as default for generic OpenAI ada-002 compatibility, but pgvector allows any size.
    # Note: User should ensure embedding dimension matches this column.
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(768))

    source_file: Mapped["SourceFile"] = relationship(back_populates="chunks")


class Job(Base):
    """
    Represents a background job for the Postgres Queue.
    """
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(50), index=True) # e.g. "summarize_project"
    payload: Mapped[str] = mapped_column(Text) # JSON string or use JSONB if supported/configured, Text is safer for generic
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True) # queued, processing, failed, completed

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Optional: Error message if failed
    error: Mapped[Optional[str]] = mapped_column(Text)
    result: Mapped[Optional[str]] = mapped_column(Text) # Result/Error


class Message(Base):
    """
    Flattened message log for full-text search.
    Populated asynchronously when messages are generated.
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    project_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(50)) # "human", "ai"
    content: Mapped[str] = mapped_column(Text)
    thinking: Mapped[Optional[str]] = mapped_column(Text) # Separate reasoning content
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sequence_number: Mapped[Optional[int]] = mapped_column(Integer)  # Thread-local ordering

    # Optional: reference to checkpoint ID if we want to linked back to graph state
    checkpoint_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # New columns for tool calls
    tool_calls: Mapped[Optional[List[dict]]] = mapped_column(JSON)
    tool_output: Mapped[Optional[str]] = mapped_column(Text)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages", primaryjoin="Message.thread_id == Conversation.id", foreign_keys=[thread_id])


class Conversation(Base):
    """
    Metadata for a conversation thread.
    """
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(255), primary_key=True) # thread_id (uuid)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[List["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", primaryjoin="Message.thread_id == Conversation.id", foreign_keys="[Message.thread_id]")
    plan: Mapped[Optional["Plan"]] = relationship(back_populates="conversation", uselist=False, cascade="all, delete-orphan")


class Tool(Base):
    """
    Represents a tool available to the agent, vectorized for semantic retrieval.
    """
    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)

    # Semantic Signature (Name + Desc + Keywords + Args)
    signature: Mapped[str] = mapped_column(Text)

    # Optional metadata
    category: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # Vector Embedding
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(768))

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class McpServer(Base):
    """
    Configuration for an MCP Server.
    """
    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    command: Mapped[str] = mapped_column(String(1024))
    args: Mapped[str] = mapped_column(Text) # Stored as JSON string list
    env: Mapped[str] = mapped_column(Text) # Stored as JSON string dict

    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TraceEvent(Base):
    """
    Represents a high-fidelity snapshot of agent execution for Imitation Learning.
    Stores State -> Action tuples.

    Supports both:
    - Agent actions (LLM/tool calls, automatically captured)
    - Human actions (UI interactions, captured via frontend ActionRecorder)
    """
    __tablename__ = "trace_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    step_number: Mapped[int] = mapped_column(Integer)

    # State Context
    node_name: Mapped[str] = mapped_column(String(100))
    state_snapshot: Mapped[dict] = mapped_column(Text) # Huge JSON of inputs/scratchpad

    # Action
    action_type: Mapped[str] = mapped_column(String(50)) # "node_start", "llm_call", "tool_call", "user_intervention", "user_click", "user_input"
    action_payload: Mapped[dict] = mapped_column(Text) # JSON of args/output/message

    # Human/Agent Distinction (Phase 1)
    is_human_action: Mapped[bool] = mapped_column(default=False) # True if action was performed by human, not agent

    # Visual Context (Phase 1)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True) # Path to screenshot taken at this moment
    ui_element_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # JSON: target element selector, text, bounds

    # Feedback & Reward
    reward: Mapped[Optional[float]] = mapped_column(Integer, nullable=True) # Normalized reward if available
    user_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # User correction/comment

    # Session Tracking
    recording_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True) # Groups events in one recording session
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # New columns for compatibility with new refactors (Nullable)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    timestamp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    event_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_selector: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class LearnedSkill(Base):
    """
    Stores learned skills synthesized from trace sequences.
    These can be matched to user intents and executed automatically.
    """
    __tablename__ = "learned_skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)

    # Matching
    trigger_patterns: Mapped[str] = mapped_column(Text)  # JSON list of trigger patterns

    # Configuration
    parameters: Mapped[str] = mapped_column(Text)  # JSON list of SkillParameter
    preconditions: Mapped[str] = mapped_column(Text, nullable=True)  # JSON list of preconditions
    steps: Mapped[str] = mapped_column(Text)  # JSON list of SkillStep
    tools_used: Mapped[str] = mapped_column(Text, nullable=True)  # JSON list of tool names

    # Source Reference
    source_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Usage Statistics
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    
    # New fields compatibility
    project_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    embedding: Mapped[Optional[List[float]]] = mapped_column(Vector(768), nullable=True)


# --- NEW TABLES START HERE ---

class MemoryConcept(Base):
    __tablename__ = "memory_concepts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    related_files: Mapped[Optional[List[str]]] = mapped_column(JSON) # List of file paths
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True) # UUID
    thread_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="active") # active, completed, archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    
    conversation: Mapped["Conversation"] = relationship(back_populates="plan")
    steps: Mapped[List["PlanStep"]] = relationship(back_populates="plan", cascade="all, delete-orphan", order_by="PlanStep.order")


class PlanStep(Base):
    __tablename__ = "plan_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True) # UUID
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending") # pending, in_progress, completed, failed
    result: Mapped[Optional[str]] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    
    plan: Mapped["Plan"] = relationship(back_populates="steps")


class HumanRequest(Base):
    """
    Stores pending human interactions (Phase 0.2)
    """
    __tablename__ = "human_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True) # UUID
    thread_id: Mapped[str] = mapped_column(String(36), index=True) # Not FK to avoid strict dependency
    type: Mapped[str] = mapped_column(String(50)) # 'input', 'confirmation', 'selection'
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending") # pending, completed, rejected
    result: Mapped[Optional[str]] = mapped_column(Text) # JSON string of user input
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProjectResource(Base):
    """
    Stores project-specific resources (pinned files, external links).
    """
    __tablename__ = "project_resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(50)) # 'file', 'link'
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text) # Relative Path or URL
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(Text, primary_key=True)
    parent_checkpoint_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(Text)
    checkpoint: Mapped[dict] = mapped_column(JSONB)
    checkpoint_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default={})


class CheckpointWrite(Base):
    __tablename__ = "checkpoint_writes"

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    checkpoint_id: Mapped[str] = mapped_column(Text, primary_key=True)
    task_id: Mapped[str] = mapped_column(Text, primary_key=True)
    idx: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(Text)
    type: Mapped[Optional[str]] = mapped_column(Text)
    blob: Mapped[bytes] = mapped_column(LargeBinary)
    task_path: Mapped[str] = mapped_column(Text, default="")


class CheckpointBlob(Base):
    __tablename__ = "checkpoint_blobs"

    thread_id: Mapped[str] = mapped_column(Text, primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, primary_key=True, default="")
    channel: Mapped[str] = mapped_column(Text, primary_key=True)
    version: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)


class CheckpointMigration(Base):
    __tablename__ = "checkpoint_migrations"

    v: Mapped[int] = mapped_column(Integer, primary_key=True)
