from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import String, Integer, ForeignKey, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from app.infrastructure.database.sql.database import Base


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # project: Mapped["Project"] = relationship(back_populates="repositories")
    files: Mapped[List["SourceFile"]] = relationship(back_populates="repository", cascade="all, delete-orphan")


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"))
    path: Mapped[str] = mapped_column(String(1024), index=True)  # Relative path in repo
    checksum: Mapped[str] = mapped_column(String(64))  # SHA256 or similar
    last_indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                      default=lambda: datetime.now(timezone.utc))

    repository: Mapped["Repository"] = relationship(back_populates="files")
    chunks: Mapped[List["CodeChunk"]] = relationship(back_populates="file", cascade="all, delete-orphan")
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
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    file: Mapped["SourceFile"] = relationship(back_populates="entities")
    
    # Self-referential or other relationships could be added here if we want explicit graph navigation in ORM
    # For now, we use a separate table for relations to be cleaner.


class CodeRelation(Base):
    __tablename__ = "code_relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # We link to entities. 
    source_entity_id: Mapped[int] = mapped_column(ForeignKey("code_entities.id"))
    target_entity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("code_entities.id"), nullable=True)
    target_name: Mapped[Optional[str]] = mapped_column(String(512), index=True) # Unresolved target name
    
    relation_type: Mapped[str] = mapped_column(String(50))  # calls, inherits, imports, defines
    
    # Optional: properties like confidence or count
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CodeChunk(Base):
    """
    Represents a chunk of code (e.g., a function, class, or block) that is vectorized.
    """
    __tablename__ = "code_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"))

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

    file: Mapped["SourceFile"] = relationship(back_populates="chunks")


class Job(Base):
    """
    Represents a background job for the Postgres Queue.
    """
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(50), index=True) # e.g. "summarize_project"
    payload: Mapped[dict] = mapped_column(Text) # JSON string or use JSONB if supported/configured, Text is safer for generic
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True) # queued, processing, failed, completed
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Optional: Error message if failed
    error: Mapped[Optional[str]] = mapped_column(Text)


class Message(Base):
    """
    Flattened message log for full-text search.
    Populated asynchronously when messages are generated.
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(50)) # "human", "ai"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Optional: reference to checkpoint ID if we want to linked back to graph state
    checkpoint_id: Mapped[Optional[str]] = mapped_column(String(255))


class Conversation(Base):
    """
    Metadata for a conversation thread.
    """
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(255), primary_key=True) # thread_id (uuid)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class McpServer(Base):
    """
    Configuration for an MCP Server.
    """
    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    command: Mapped[str] = mapped_column(String(1024))
    args: Mapped[List[str]] = mapped_column(Text) # Stored as JSON string list
    env: Mapped[dict] = mapped_column(Text) # Stored as JSON string dict
    
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
