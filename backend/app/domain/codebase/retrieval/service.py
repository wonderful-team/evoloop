from typing import Any

from sqlalchemy import select

from app.core.context.manager import ContextManager
from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.infrastructure.embeddings.factory import EmbedderFactory
from app.models import (
    CodeEntity,
    CodeRelation,
    Repository,
    SourceFile,
)


class RetrievalService:
    def __init__(self, embedder=None):
        self.session_factory = AsyncSessionLocal
        self.embedder = embedder or EmbedderFactory.get_embedder()

    async def search(self, query: str, project_id: int = None, limit: int = 5) -> list[dict[str, Any]]:
        """
        Search for code chunks using Hybrid Search (Vector + Keyword) via RRF.
        """
        # Resolve project_id from context if not provided
        pid = project_id or ContextManager.current().project_id

        from app.domain.codebase.retrieval.hybrid import hybrid_searcher

        return await hybrid_searcher.search(query, project_id=pid, limit=limit)

    async def get_entity_relations(self, symbol_name: str, project_id: int = None) -> dict[str, Any]:
        """
        Get relations (inheritance, calls) for a specific symbol.
        """
        pid = project_id or ContextManager.current().project_id

        async with self.session_factory() as session:
            # 1. Find the entity
            # Try exact match first, then ilike
            stmt = select(CodeEntity).where(CodeEntity.name == symbol_name)

            # Filter by project if provided (requires join)
            if pid:
                stmt = stmt.join(SourceFile).join(Repository).where(Repository.project_id == pid)

            stmt = stmt.limit(1)
            result = await session.execute(stmt)
            entity = result.scalar_one_or_none()

            if not entity:
                # Try fuzzy
                stmt = select(CodeEntity).where(CodeEntity.name.ilike(f"%{symbol_name}%"))
                if pid:
                    stmt = stmt.join(SourceFile).join(Repository).where(Repository.project_id == pid)
                stmt = stmt.limit(1)
                result = await session.execute(stmt)
                entity = result.scalar_one_or_none()

            if not entity:
                return {"error": f"Symbol '{symbol_name}' not found."}

            # 2. Find Outgoing Relations (This entity mentions others)
            # source_entity_id == entity.id
            # Join target entity to get names

            # We need explicit aliases or just load generic
            # Relations where I am the source
            out_stmt = (
                select(CodeRelation, CodeEntity)
                .outerjoin(CodeEntity, CodeRelation.target_entity_id == CodeEntity.id)
                .where(CodeRelation.source_entity_id == entity.id)
            )

            out_rows = (await session.execute(out_stmt)).all()

            outgoing = []
            for rel, target_ent in out_rows:
                target_name = target_ent.full_name if target_ent else rel.target_name
                outgoing.append(f"{rel.relation_type} -> {target_name}")

            # 3. Find Incoming Relations (Others mention me)
            # target_entity_id == entity.id
            in_stmt = (
                select(CodeRelation, CodeEntity)
                .join(CodeEntity, CodeRelation.source_entity_id == CodeEntity.id)
                .where(CodeRelation.target_entity_id == entity.id)
            )

            in_rows = (await session.execute(in_stmt)).all()

            incoming = []
            for rel, source_ent in in_rows:
                source_name = source_ent.full_name
                incoming.append(f"{source_name} -> {rel.relation_type}")

            return {
                "symbol": entity.full_name,
                "type": entity.type,
                "file": entity.file.path if entity.file else "unknown",  # Requires eager load or lazy load session
                "relations": {"outgoing": outgoing, "incoming": incoming},
            }
