from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.models.app_map import AppMap


class Repository(Base):
    __tablename__ = "repositories"

    __table_args__ = (
        Index(
            "ux_repositories_active_project_id",
            "project_id",
            unique=True,
            postgresql_where=text("sync_status NOT IN ('IGNORED', 'DISCONNECTED')"),
            sqlite_where=text("sync_status NOT IN ('IGNORED', 'DISCONNECTED')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # project_id is now a loose reference to the external project ID
    # We index it for faster lookups, but DO NOT enforce foreign key constraint to a local table
    project_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # Owner member ID for multi-user isolation
    member_id: Mapped[int] = mapped_column(Integer, default=0, index=True)

    # Sync Status:
    # - "DETECTED": Newly detected, awaiting user confirmation
    # - "IGNORED": User chose to ignore
    # - "PENDING_CREATION": User confirmed, awaiting cloud sync
    # - "SYNCED": Successfully synced with cloud
    # - "DISCONNECTED": Local directory deleted
    sync_status: Mapped[str] = mapped_column(String(50), default="DETECTED")

    # Indexing Status:
    # - "pending": Waiting to be indexed
    # - "in_progress": Currently being indexed
    # - "completed": Successfully indexed
    # - "failed": Indexing failed
    # - "not_needed": Sync status is DETECTED/IGNORED, no indexing needed
    indexing_status: Mapped[str] = mapped_column(String(50), default="pending")
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Detection and import timestamps
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1024))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(String(1024))
    relative_path: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    files: Mapped[list["SourceFile"]] = relationship(back_populates="repository", cascade="all, delete-orphan")


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"))
    path: Mapped[str] = mapped_column(String(1024), index=True)  # Relative path in repo
    checksum: Mapped[str] = mapped_column(String(64))  # SHA256 or similar
    last_indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    scan_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | completed | failed
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    security_scan_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | completed | failed

    repository: Mapped["Repository"] = relationship(back_populates="files")
    chunks: Mapped[list["CodeChunk"]] = relationship(back_populates="source_file", cascade="all, delete-orphan")
    entities: Mapped[list["CodeEntity"]] = relationship(back_populates="file", cascade="all, delete-orphan")
    security_findings: Mapped[list["SecurityFinding"]] = relationship(back_populates="source_file", cascade="all, delete-orphan")


class CodeEntity(Base):
    __tablename__ = "code_entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"))

    name: Mapped[str] = mapped_column(String(1024), index=True)
    type: Mapped[str] = mapped_column(String(50))  # class, function, variable
    full_name: Mapped[str] = mapped_column(String(1024), index=True)  # FQN, e.g. module.Class.method

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
    target_name: Mapped[str | None] = mapped_column(String(1024), index=True)  # Unresolved target name

    relation_type: Mapped[str] = mapped_column(String(50))  # calls, inherits, imports, defines
    confidence: Mapped[str] = mapped_column(String(20), default="EXTRACTED")  # EXTRACTED | INFERRED | AMBIGUOUS

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source_entity: Mapped["CodeEntity"] = relationship(
        "CodeEntity",
        foreign_keys=[source_entity_id],
        back_populates="relations_from"
    )
    target_entity: Mapped["CodeEntity | None"] = relationship(
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
    identifier: Mapped[str] = mapped_column(String(1024))  # e.g. "MyClass.my_method"
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)

    # Semantic flags populated by APIExtractor / DBExtractor
    is_api_route: Mapped[bool] = mapped_column(default=False)
    api_method: Mapped[str | None] = mapped_column(String(10), nullable=True)  # GET/POST/PUT/DELETE
    api_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_db_model: Mapped[bool] = mapped_column(default=False)
    db_table_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    source_file: Mapped["SourceFile"] = relationship(back_populates="chunks")
    app_map_links: Mapped[list["AppMapRouteLink"]] = relationship(
        "AppMapRouteLink", back_populates="code_chunk"
    )


class SecurityFinding(Base):
    """Security vulnerability discovered during indexing."""

    __tablename__ = "security_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_file_id: Mapped[int] = mapped_column(ForeignKey("source_files.id"), index=True)
    finding_type: Mapped[str] = mapped_column(String(50))  # sql_injection | path_traversal | command_injection | hardcoded_secret | ssrf
    severity: Mapped[str] = mapped_column(String(10), default="medium")  # critical | high | medium | low
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source_file: Mapped["SourceFile"] = relationship(back_populates="security_findings")


class AppMapRouteLink(Base):
    """Links AppMap entities to the CodeChunk routes/models that back them."""

    __tablename__ = "app_map_route_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    app_map_id: Mapped[int] = mapped_column(ForeignKey("app_maps.id"), index=True)
    code_chunk_id: Mapped[int | None] = mapped_column(ForeignKey("code_chunks.id"), nullable=True)
    relation_kind: Mapped[str] = mapped_column(String(20))  # route | action | db_table
    logical_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    logical_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_verified: Mapped[bool] = mapped_column(default=False)

    app_map: Mapped["AppMap"] = relationship(back_populates="route_links")
    code_chunk: Mapped["CodeChunk | None"] = relationship(back_populates="app_map_links")
