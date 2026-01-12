from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class Job(Base):
    """
    Represents a background job for the Postgres Queue.
    """
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(50), index=True)  # e.g. "summarize_project"
    payload: Mapped[str] = mapped_column(Text)  # JSON string or use JSONB if supported/configured, Text is safer for generic
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued, processing, failed, completed

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Optional: Error message if failed
    error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text)  # Result/Error


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
    category: Mapped[str | None] = mapped_column(String(100), index=True)

    # Vector Embedding
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class McpServer(Base):
    """
    Configuration for an MCP Server.
    """
    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    command: Mapped[str] = mapped_column(String(1024))
    args: Mapped[str] = mapped_column(Text)  # Stored as JSON string list
    env: Mapped[str] = mapped_column(Text)  # Stored as JSON string dict

    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProjectResource(Base):
    """
    Stores project-specific resources (pinned files, external links).
    """
    __tablename__ = "project_resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(50))  # 'file', 'link'
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)  # Relative Path or URL
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
