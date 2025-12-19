from typing import List, Dict, Any
from sqlalchemy import select, text
from app.infrastructure.database.sql.database import AsyncSessionLocal
from app.infrastructure.database.sql.models import CodeChunk, SourceFile, Repository
from app.domain.codebase.indexing.vectors.openai_embedder import OpenAIEmbedder
from app.logging import logger


class RetrievalService:
    def __init__(self, embedder=None):
        self.session_factory = AsyncSessionLocal
        self.embedder = embedder or OpenAIEmbedder()

    async def search(self, query: str, project_id: int = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for code chunks semantically similar to the query.
        """
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

            if project_id:
                stmt = stmt.where(Repository.project_id == project_id)

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
                    "score": 1 - distance  # Convert L2 distance to similarity score (approx)
                })

            return results
