from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Get embedding dimension from settings (Single Source of Truth)
from app.core.config import settings
from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow

EMBEDDING_DIM = settings.EMBEDDING_DIMENSIONS


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    # project_id is now a loose reference to the external project ID
    # We index it for faster lookups, but DO NOT enforce foreign key constraint to a local table
    project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # Sync Status: SYNCED, PENDING_CREATION, DISCONNECTED
    sync_status: Mapped[str] = mapped_column(String(50), default="SYNCED")

    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024))
    local_path: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    files: Mapped[list["SourceFile"]] = relationship(back_populates="repository", cascade="all, delete-orphan")


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"))
    path: Mapped[str] = mapped_column(String(1024), index=True)  # Relative path in repo
    checksum: Mapped[str] = mapped_column(String(64))  # SHA256 or similar
    last_indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    repository: Mapped["Repository"] = relationship(back_populates="files")
    chunks: Mapped[list["CodeChunk"]] = relationship(back_populates="source_file", cascade="all, delete-orphan")
    entities: Mapped[list["CodeEntity"]] = relationship(back_populates="file", cascade="all, delete-orphan")


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
    relations_from: Mapped[list["CodeRelation"]] = relationship(
        "CodeRelation",
        foreign_keys="CodeRelation.source_entity_id",
        back_populates="source_entity",
        cascade="all, delete-orphan",
    )
    relations_to: Mapped[list["CodeRelation"]] = relationship(
        "CodeRelation",
        foreign_keys="CodeRelation.target_entity_id",
        back_populates="target_entity",
        cascade="all, delete-orphan",
    )


class CodeRelation(Base):
    __tablename__ = "code_relations"

    id: Mapped[int] = mapped_column(primary_key=True)

    source_entity_id: Mapped[int] = mapped_column(ForeignKey("code_entities.id"))
    target_entity_id: Mapped[int | None] = mapped_column(ForeignKey("code_entities.id"), nullable=True)
    target_name: Mapped[str | None] = mapped_column(String(512), index=True)  # Unresolved target name

    relation_type: Mapped[str] = mapped_column(String(50))  # calls, inherits, imports, defines

    # Optional: properties like confidence or count

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source_entity: Mapped["CodeEntity"] = relationship(
        "CodeEntity",
        foreign_keys=[source_entity_id],
        back_populates="relations_from"
    )
    target_entity: Mapped[Optional["CodeEntity"]] = relationship(
        "CodeEntity",
        foreign_keys=[target_entity_id],
        back_populates="relations_to"
    )


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

    # Vector Embedding
    # Using configured dimension (default 1536 for OpenAI)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    source_file: Mapped["SourceFile"] = relationship(back_populates="chunks")
