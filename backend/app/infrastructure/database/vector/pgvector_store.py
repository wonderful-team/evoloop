"""
PgVectorStore — PostgreSQL + pgvector implementation for production mode.

Uses a dedicated PostgreSQL instance (or separate database) for vector storage.
Schema is managed via Alembic migrations; the store only ensures the pgvector
extension is present and tables exist as a fallback.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.core.config import settings
from app.core.file import compute_md5
from app.infrastructure.database.vector.base import BaseVectorStore
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

EMBEDDING_DIM = settings.EMBEDDING_DIMENSIONS

# ---------------------------------------------------------------------------
# SQLAlchemy model for the unified vector table (separate metadata so Alembic
# can target it independently).
# ---------------------------------------------------------------------------


class VectorBase(DeclarativeBase):
    pass


class VectorEmbedding(VectorBase):
    __tablename__ = "vector_embeddings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    collection: Mapped[str | None] = mapped_column(String(100))
    embedding: Mapped[Any] = mapped_column(
        # pgvector.Vector is imported lazily so that importing this module
        # does not fail when pgvector is not installed (e.g. embedded mode).
        # The actual column type is resolved at runtime inside _ensure_schema().
        Text,
        nullable=False,
    )
    content: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

    __table_args__ = (
        Index("idx_vec_source", "source_type", "source_id"),
        Index("idx_vec_collection", "collection"),
    )


# ---------------------------------------------------------------------------
# PgVectorStore implementation
# ---------------------------------------------------------------------------


class PgVectorStore(BaseVectorStore):
    """Production vector store backed by PostgreSQL + pgvector."""

    def __init__(self, db_uri: str | None = None):
        db_uri = db_uri or settings.VECTOR_DATABASE_URI
        if not db_uri:
            raise RuntimeError(
                "VECTOR_DATABASE_URI is not configured. "
                "Set VECTOR_POSTGRES_* variables or run in embedded mode."
            )
        # Use synchronous SQLAlchemy (callers invoke us synchronously).
        self._db_uri = db_uri
        self._engine = create_engine(
            db_uri,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT},
        )
        self._embedding_dim = EMBEDDING_DIM
        self._ensure_schema()
        logger.info(f"[PgVectorStore] Connected to {db_uri}")

    # -- internal helpers ---------------------------------------------------

    def _ensure_schema(self) -> None:
        """Create extension, table and IVFFlat index if missing."""
        from pgvector.sqlalchemy import Vector

        # Fix column type to real pgvector.Vector (it was declared as Text
        # above to avoid an import-time dependency on pgvector).
        VectorEmbedding.__table__.c.embedding.type = Vector(self._embedding_dim)

        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            VectorBase.metadata.create_all(conn)
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_vec_embedding ON vector_embeddings "
                    "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
                )
            )

    def _session(self) -> Session:
        return Session(self._engine)

    # -- code chunks --------------------------------------------------------

    def upsert_code_chunks(
        self,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> int:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have same length")
        if not chunks:
            return 0

        now = utcnow()
        with self._session() as session:
            for chunk, emb in zip(chunks, embeddings, strict=False):
                chunk_id = compute_md5(f"{chunk['file_path']}:{chunk['start_line']}:{chunk['content'][:100]}")
                existing = session.query(VectorEmbedding).filter_by(
                    source_type="code_chunk", source_id=chunk_id
                ).first()
                if existing:
                    existing.embedding = emb
                    existing.content = chunk["content"]
                    existing.metadata_ = chunk
                    existing.created_at = now
                else:
                    session.add(
                        VectorEmbedding(
                            source_type="code_chunk",
                            source_id=chunk_id,
                            collection=chunk.get("repository_id"),
                            embedding=emb,
                            content=chunk["content"],
                            metadata_=chunk,
                            created_at=now,
                        )
                    )
            session.commit()

        logger.debug(f"[PgVectorStore] Upserted {len(chunks)} code chunks")
        return len(chunks)

    def search_code(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: str | None = None,
        repository_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._session() as session:
            # cosine_distance returns a float; smaller = more similar.
            # We order ascending and convert to similarity score (1 - distance).
            emb_col = VectorEmbedding.embedding
            q = (
                session.query(
                    VectorEmbedding,
                    emb_col.cosine_distance(query_vector).label("distance"),
                )
                .filter(VectorEmbedding.source_type == "code_chunk")
                .order_by(emb_col.cosine_distance(query_vector))
                .limit(top_k)
            )

            if repository_id:
                q = q.filter(
                    VectorEmbedding.collection == repository_id
                )

            rows = q.all()

            return [
                {
                    "id": r.VectorEmbedding.source_id,
                    "content": r.VectorEmbedding.content,
                    "file_path": r.VectorEmbedding.metadata_.get("file_path", ""),
                    "repository_id": r.VectorEmbedding.collection or "",
                    "chunk_type": r.VectorEmbedding.metadata_.get("chunk_type", "unknown"),
                    "identifier": r.VectorEmbedding.metadata_.get("identifier", ""),
                    "start_line": r.VectorEmbedding.metadata_.get("start_line", 0),
                    "end_line": r.VectorEmbedding.metadata_.get("end_line", 0),
                    "language": r.VectorEmbedding.metadata_.get("language", "unknown"),
                    "score": 1.0 - float(r.distance),
                }
                for r in rows
            ]

    def delete_by_repository(self, repository_id: str) -> int:
        with self._session() as session:
            count = (
                session.query(VectorEmbedding)
                .filter(VectorEmbedding.source_type == "code_chunk")
                .filter(VectorEmbedding.collection == repository_id)
                .delete(synchronize_session=False)
            )
            session.commit()
            logger.debug(f"[PgVectorStore] Deleted {count} code chunks for repo {repository_id}")
            return count

    # -- memories -----------------------------------------------------------

    def search_memory(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        with self._session() as session:
            emb_col = VectorEmbedding.embedding
            q = (
                session.query(
                    VectorEmbedding,
                    emb_col.cosine_distance(query_vector).label("distance"),
                )
                .filter(VectorEmbedding.source_type == "memory")
                .order_by(emb_col.cosine_distance(query_vector))
                .limit(top_k)
            )

            if filters:
                if "project_id" in filters and filters["project_id"] is not None:
                    q = q.filter(VectorEmbedding.collection == str(filters["project_id"]))
                if "member_id" in filters and filters["member_id"] is not None:
                    # In PgVectorStore, member_id is inside the JSONB metadata column
                    q = q.filter(VectorEmbedding.metadata_["member_id"].astext == str(filters["member_id"]))

            rows = q.all()

            return [
                {
                    "id": r.VectorEmbedding.source_id,
                    "text": r.VectorEmbedding.content,
                    "project_id": r.VectorEmbedding.metadata_.get("project_id"),
                    "member_id": r.VectorEmbedding.metadata_.get("member_id"),
                    "score": 1.0 - float(r.distance),
                }
                for r in rows
            ]

    # -- skills -----------------------------------------------------------

    def search_skills(
        self,
        query_vector: list[float],
        bundle_id: str | None = None,
        platform: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        with self._session() as session:
            emb_col = VectorEmbedding.embedding
            q = (
                session.query(
                    VectorEmbedding,
                    emb_col.cosine_distance(query_vector).label("distance"),
                )
                .filter(VectorEmbedding.source_type == "skill")
                .order_by(emb_col.cosine_distance(query_vector))
                .limit(top_k)
            )

            if bundle_id:
                q = q.filter(VectorEmbedding.metadata_["bundle_id"].astext == bundle_id)
            if platform:
                q = q.filter(VectorEmbedding.metadata_["platform"].astext == platform)

            rows = q.all()

            return [
                {
                    "id": r.VectorEmbedding.source_id,
                    "name": r.VectorEmbedding.metadata_.get("name", ""),
                    "description": r.VectorEmbedding.content,
                    "bundle_id": r.VectorEmbedding.metadata_.get("bundle_id"),
                    "platform": r.VectorEmbedding.metadata_.get("platform"),
                    "score": 1.0 - float(r.distance),
                }
                for r in rows
            ]

    # -- concepts ---------------------------------------------------------

    def search_concepts(self, query_vector: list[float], top_k: int = 10) -> list[dict[str, Any]]:
        with self._session() as session:
            emb_col = VectorEmbedding.embedding
            rows = (
                session.query(
                    VectorEmbedding,
                    emb_col.cosine_distance(query_vector).label("distance"),
                )
                .filter(VectorEmbedding.source_type == "concept")
                .order_by(emb_col.cosine_distance(query_vector))
                .limit(top_k)
                .all()
            )

            return [
                {
                    "id": r.VectorEmbedding.source_id,
                    "name": r.VectorEmbedding.metadata_.get("name", ""),
                    "description": r.VectorEmbedding.content,
                    "score": 1.0 - float(r.distance),
                }
                for r in rows
            ]

    # -- maintenance --------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        with self._session() as session:
            total = session.query(VectorEmbedding).count()
            code_count = (
                session.query(VectorEmbedding)
                .filter(VectorEmbedding.source_type == "code_chunk")
                .count()
            )
            mem_count = (
                session.query(VectorEmbedding)
                .filter(VectorEmbedding.source_type == "memory")
                .count()
            )
            skill_count = (
                session.query(VectorEmbedding)
                .filter(VectorEmbedding.source_type == "skill")
                .count()
            )
            concept_count = (
                session.query(VectorEmbedding)
                .filter(VectorEmbedding.source_type == "concept")
                .count()
            )
            return {
                "backend": "pgvector",
                "db_uri": self._db_uri,
                "total_vectors": total,
                "code_chunks": code_count,
                "memories": mem_count,
                "skills": skill_count,
                "concepts": concept_count,
                "embedding_dim": self._embedding_dim,
            }

    def compact(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(text("VACUUM ANALYZE vector_embeddings"))
            logger.info("[PgVectorStore] VACUUM ANALYZE completed")

    def truncate_all(self) -> None:
        """Wipe all data from the unified vector table."""
        with self._session() as session:
            session.execute(text("TRUNCATE TABLE vector_embeddings CASCADE"))
            session.commit()
        logger.info("[PgVectorStore] All vectors truncated")

    def close(self) -> None:
        """Dispose the underlying SQLAlchemy engine."""
        self._engine.dispose()
        logger.info("[PgVectorStore] Engine disposed")
