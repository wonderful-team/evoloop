from typing import List, Dict, Any

from sqlalchemy import select

from app.domain.codebase.indexing.vectors.openai_embedder import OpenAIEmbedder
from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.infrastructure.database.sql.models import CodeChunk, SourceFile, Repository, CodeEntity, CodeRelation


from app.logging import get_context

class RetrievalService:
    def __init__(self, embedder=None):
        self.session_factory = AsyncSessionLocal
        self.embedder = embedder or OpenAIEmbedder()

    async def search(self, query: str, project_id: int = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for code chunks semantically similar to the query.
        """
        # Resolve project_id from context if not provided
        pid = project_id or get_context().get("project_id")

        # 1. Embed Query
        query_embedding = await self.embedder.embed_query(query)

        async with self.session_factory() as session:
            # 2. Vector Search using pgvector
            # Syntax: CodeChunk.embedding.l2_distance(query_embedding)
            # We select the distance as a column to return it
            distance_col = CodeChunk.embedding.l2_distance(query_embedding).label("distance")

            stmt = select(CodeChunk, SourceFile, distance_col) \
                .join(SourceFile) \
                .join(Repository, SourceFile.repository_id == Repository.id)

            if pid:
                stmt = stmt.where(Repository.project_id == pid)

            stmt = stmt.order_by(distance_col).limit(limit)

            result = await session.execute(stmt)
            rows = result.all()

            results = []
            for chunk, file, distance in rows:
                results.append({
                    "file_path": file.path,
                    "chunk_type": chunk.chunk_type,
                    "identifier": chunk.identifier,
                    "content": chunk.content,
                })

            return results

    async def get_entity_relations(self, symbol_name: str, project_id: int = None) -> Dict[str, Any]:
        """
        Get relations (inheritance, calls) for a specific symbol.
        """
        pid = project_id or get_context().get("project_id")
        
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
            out_stmt = select(CodeRelation, CodeEntity).outerjoin(CodeEntity, CodeRelation.target_entity_id == CodeEntity.id)\
                        .where(CodeRelation.source_entity_id == entity.id)
            
            out_rows = (await session.execute(out_stmt)).all()
            
            outgoing = []
            for rel, target_ent in out_rows:
                target_name = target_ent.full_name if target_ent else rel.target_name
                outgoing.append(f"{rel.relation_type} -> {target_name}")

            # 3. Find Incoming Relations (Others mention me)
            # target_entity_id == entity.id
            in_stmt = select(CodeRelation, CodeEntity).join(CodeEntity, CodeRelation.source_entity_id == CodeEntity.id)\
                       .where(CodeRelation.target_entity_id == entity.id)
            
            in_rows = (await session.execute(in_stmt)).all()
            
            incoming = []
            for rel, source_ent in in_rows:
                source_name = source_ent.full_name
                incoming.append(f"{source_name} -> {rel.relation_type}")
                
            return {
                "symbol": entity.full_name,
                "type": entity.type,
                "file": entity.file.path if entity.file else "unknown", # Requires eager load or lazy load session
                "relations": {
                    "outgoing": outgoing,
                    "incoming": incoming
                }
            }
