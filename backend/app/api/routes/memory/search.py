import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import CurrentUserOptional
from app.api.schemas.memory import (
    ConceptResponse,
    HybridResultItem,
    HybridSearchResponse,
    VectorSearchResponse,
    VectorSearchResult,
)
from app.core.memory.models import MemoryType
from app.infrastructure.database.vector import get_vector_store
from app.infrastructure.embeddings.factory import EmbedderFactory

from .shared import get_memory_manager

router = APIRouter()

logger = logging.getLogger(__name__)


async def _perform_vector_search(
    query: str,
    project_id: int | None = None,
    project_path: str | None = None,
    top_k: int = 10,
    repository_id: str | None = None,
) -> list[dict[str, Any]]:
    embedder = EmbedderFactory.get_embedder()
    if embedder is None:
        logger.warning("Semantic search unavailable: no embedding provider configured.")
        return []

    query_embedding = await embedder.aembed_query(query)

    if project_path is None and project_id is not None:
        from app.core.project.utils import get_project_path

        project_path = await get_project_path(project_id)

    vector_store = get_vector_store(project_path=project_path)

    repo_filter = repository_id
    if not repo_filter and project_id:
        repo_filter = str(project_id)

    results = await asyncio.to_thread(
        vector_store.search_code,
        query_vector=query_embedding,
        top_k=top_k,
        repository_id=repo_filter,
    )

    return results


@router.get("/search", response_model=list[ConceptResponse])
async def search_memory(
    q: str,
    project_id: int | None = None,
    _use_vector: bool = Query(
        False, description="Use vector similarity search if available"
    ),
    manager=Depends(get_memory_manager),
    current_user: CurrentUserOptional = None,
):
    if not q:
        return []

    results = await manager.search_memories(
        query=q,
        types=[MemoryType.CONCEPT],
        project_id=project_id,
        limit=10,
        member_id=current_user.id if current_user else 0,
    )
    return [
        ConceptResponse(name=r.title, description=r.description, episode_count=0)
        for r in results
    ]


@router.get("/search/vector", response_model=VectorSearchResponse)
async def search_memory_vector(
    q: str,
    project_id: int | None = None,
    top_k: int = Query(10, ge=1, le=50),
    repository_id: str | None = None,
):
    if not q:
        return VectorSearchResponse(results=[], total=0, query=q, search_type="vector")

    try:
        results = await _perform_vector_search(q, project_id, top_k, repository_id)

        search_results = [
            VectorSearchResult(
                id=r["id"],
                content=r["content"],
                file_path=r["file_path"],
                repository_id=r["repository_id"],
                chunk_type=r["chunk_type"],
                identifier=r["identifier"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                language=r["language"],
                score=r["score"],
            )
            for r in results
        ]

        return VectorSearchResponse(
            results=search_results,
            total=len(search_results),
            query=q,
            search_type="vector",
        )

    except Exception as e:
        logger.exception(f"Vector search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Vector search failed: {str(e)}")


@router.get("/search/hybrid", response_model=HybridSearchResponse)
async def search_memory_hybrid(
    q: str,
    project_id: int | None = None,
    top_k: int = Query(10, ge=1, le=50),
    vector_weight: float = Query(0.7, ge=0, le=1),
    manager=Depends(get_memory_manager),
    current_user: CurrentUserOptional = None,
):
    if not q:
        return HybridSearchResponse(
            results=[], total=0, query=q or "", search_type="hybrid"
        )

    try:
        vector_results = await _perform_vector_search(q, project_id, top_k * 2)

        results = await manager.search_memories(
            query=q,
            types=[MemoryType.CONCEPT],
            project_id=project_id,
            limit=top_k,
            member_id=current_user.id if current_user else 0,
        )
        text_results = [
            {"name": r.title, "description": r.description} for r in results
        ]

        combined_results = []
        seen_ids = set()

        for r in vector_results:
            if r["id"] not in seen_ids:
                combined_results.append(
                    HybridResultItem(
                        type="vector", score=r["score"] * vector_weight, data=r
                    )
                )
                seen_ids.add(r["id"])

        for r in text_results:
            result_id = f"text_{r['name']}"
            if result_id not in seen_ids:
                combined_results.append(
                    HybridResultItem(
                        type="text",
                        score=(1 - vector_weight) * 0.8,
                        data=r,
                    )
                )
                seen_ids.add(result_id)

        combined_results.sort(key=lambda x: x["score"], reverse=True)
        final_results = combined_results[:top_k]

        return HybridSearchResponse(
            results=final_results,
            total=len(final_results),
            query=q,
            search_type="hybrid",
            vector_results_count=len(vector_results),
            text_results_count=len(text_results),
        )

    except Exception as e:
        logger.exception(f"Hybrid search failed: {e}")
        text_results = await manager.search_concepts_data(
            q,
            project_id,
            member_id=current_user.id if current_user else 0
        )
        return HybridSearchResponse(
            results=[
                HybridResultItem(type="text", score=1.0, data=r) for r in text_results
            ],
            total=len(text_results),
            query=q,
            search_type="text_fallback",
        )
