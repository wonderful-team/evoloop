import asyncio
from typing import Any, Literal

from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.domain.codebase.retrieval.rewriter import query_rewriter
from app.infrastructure.database import session_scope
from app.infrastructure.database.vector import get_vector_store
from app.infrastructure.embeddings.factory import EmbedderFactory
from app.models import CodeChunk, Repository, SourceFile


class HybridSearcher:
    """
    Combines Vector Search (Semantic) and Keyword Search (Lexical) using RRF.
    """

    def __init__(self, embedder=None):
        self.session_factory = session_scope
        self.embedder = embedder or EmbedderFactory.get_embedder()

    async def search(
        self,
        query: str,
        operator: Literal["and", "or"],
        project_id: int = None,
        project_path: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        # 1. Expand Query (for Vector Search mainly, but keywords also useful)
        # For keyword search, we might want the original term + synonyms, but 'rewritten' usually is a sentence.
        # Let's use the rewritten query for Vector, and extract keywords from it or usage original?
        # Better: Usage rewritten for Vector. Usage Original + extra keywords for Lexical?
        # Simple start: Usage rewriten for Vector. Usage Original for Lexical.

        expanded_query = await query_rewriter.rewrite(query)

        # 2. Parallel Search (Simulated via sequential await for now)
        vector_results = await self._vector_search(
            expanded_query, project_id, project_path=project_path, limit=limit * 2
        )
        keyword_results = await self._keyword_search(
            query, project_id, limit=limit * 2, operator=operator
        )

        # 3. RRF Fusion
        fused = self._rrf_fusion(vector_results, keyword_results, k=60)

        # 4. Format Output
        return fused[:limit]

    async def _vector_search(
        self,
        query: str,
        project_id: int,
        project_path: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """
        Perform vector similarity search.

        Args:
            query: Search query
            project_id: Project ID for filtering
            project_path: 项目本地路径（用于获取项目级 vector store）
            limit: Maximum results
        """
        if self.embedder is None:
            return []
        query_embedding = await self.embedder.embed_query(query)
        vector_store = get_vector_store(project_path=project_path)
        candidates = await asyncio.to_thread(
            vector_store.search_code,
            query_vector=query_embedding,
            top_k=limit * 2,
        )

        # If project filtering is needed, filter by repository ownership
        if project_id is not None and project_id != DEFAULT_PROJECT_ID:
            async with self.session_factory() as session:
                repo_ids = await session.scalars(
                    select(Repository.id).where(Repository.project_id == project_id)
                )
                allowed_repo_ids = {str(r) for r in repo_ids.all()}
                candidates = [
                    c for c in candidates
                    if c.get("repository_id") in allowed_repo_ids
                ]

        return candidates[:limit]

    async def _keyword_search(
        self,
        query: str,
        operator: Literal["and", "or"],
        project_id: int,
        limit: int,
    ) -> list[dict]:
        # Simple ILIKE or pg_trgm
        # We assume pg_trgm is enabled for 'content' or we usage ILIKE for portability if not.
        # Let's usage ILIKE for robustness if pg_trgm not strictly guaranteed yet.
        # Split query into terms?
        terms = [t for t in query.split() if len(t) > 2]  # Filter noise
        if not terms:
            terms = [query]

        async with self.session_factory() as session:
            stmt = (
                select(CodeChunk, SourceFile)
                .join(SourceFile)
                .join(Repository, SourceFile.repository_id == Repository.id)
            )

            # Note: project_id can be DEFAULT_PROJECT_ID/0 (global mode), skip filter in that case
            if project_id is not None and project_id != DEFAULT_PROJECT_ID:
                stmt = stmt.where(Repository.project_id == project_id)

            # Construct conditions for terms based on operator
            # operator="and": all terms must match (AND logic)
            # operator="or": any term can match (OR logic, default)

            conditions = []
            for term in terms:
                conditions.append(CodeChunk.content.ilike(f"%{term}%"))

            from sqlalchemy import and_, or_

            if conditions:
                if operator == "and":
                    stmt = stmt.where(and_(*conditions))
                else:
                    stmt = stmt.where(or_(*conditions))

            stmt = stmt.limit(limit)

            rows = (await session.execute(stmt)).all()

            results = []
            for chunk, file in rows:
                results.append(
                    {
                        "id": chunk.id,
                        "file_path": file.path,
                        "identifier": chunk.identifier,
                        "content": chunk.content,
                        "chunk_type": chunk.chunk_type,
                        "score": 1.0,  # Base score for keyword match
                    }
                )
            return results

    def _rrf_fusion(
        self, vector_results: list[dict], keyword_results: list[dict], k: int = 60
    ) -> list[dict]:
        """
        Reciprocal Rank Fusion.
        score = sum(1 / (k + rank_i))
        """
        scores = {}
        # metadata = {}
        # Map ID to item
        items_map = {}

        # 1. Process Vector Ranks
        for rank, item in enumerate(vector_results):
            doc_id = item["id"]
            if doc_id not in items_map:
                items_map[doc_id] = item

            scores[doc_id] = scores.get(doc_id, 0) + (1 / (k + rank + 1))

        # 2. Process Keyword Ranks
        for rank, item in enumerate(keyword_results):
            doc_id = item["id"]
            if doc_id not in items_map:
                items_map[doc_id] = item

            scores[doc_id] = scores.get(doc_id, 0) + (1 / (k + rank + 1))

        # 3. Sort by fused score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        results = []
        for doc_id in sorted_ids:
            item = items_map[doc_id]
            # Optionally attach score metadata
            # item["rrf_score"] = scores[doc_id]
            results.append(item)

        return results


# Global Instance
hybrid_searcher = HybridSearcher()
