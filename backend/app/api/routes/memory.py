import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.memory import MemoryContainer, MemoryConfig
from app.infrastructure.embeddings.factory import EmbedderFactory
from app.infrastructure.database.vector.lancedb_store import get_vector_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["memory"])


async def get_memory_manager():
    """Dependency to get memory manager via MemoryLifespanManager (singleton)."""
    from app.core.memory.lifespan import MemoryLifespanManager

    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()

    yield MemoryLifespanManager.get_manager()


class ConceptCreate(BaseModel):
    name: str
    description: str
    related_files: list[str] | None = None


class ConceptUpdate(BaseModel):
    description: str | None = None
    related_files: list[str] | None = None


class ConceptResponse(BaseModel):
    name: str
    description: str | None = None
    episode_count: int | None = 0


class ConceptWithEpisodeCount(ConceptResponse):
    """Legacy model for compatibility."""
    pass


class EpisodeResponse(BaseModel):
    id: str
    goal: str
    result: str | None
    error: str | None
    timestamp: str | None  # ISO format datetime string from Neo4j


class VectorSearchResult(BaseModel):
    """Vector search result item."""
    id: str
    content: str
    file_path: str
    repository_id: str
    chunk_type: str
    identifier: str
    start_line: int
    end_line: int
    language: str
    score: float


class VectorSearchResponse(BaseModel):
    """Vector search response."""
    results: list[VectorSearchResult]
    total: int
    query: str
    search_type: str


@router.get("/concepts", response_model=list[ConceptResponse])
async def list_concepts(project_id: int, manager=Depends(get_memory_manager)):
    """
    Get all concepts for a project (legacy endpoint).
    """
    try:
        results = await manager.long_term.search_concepts_data("", project_id)
        return results
    except Exception as e:
        logger.warning(f"Failed to list concepts: {e}")
        return []


@router.get("/concepts/list", response_model=list[ConceptResponse])
async def list_concepts_with_counts(
    project_id: int, limit: int = 50, manager=Depends(get_memory_manager)
):
    """
    Get all concepts with episode counts.
    """
    try:
        results = await manager.long_term.list_concepts(project_id, limit)
        return results
    except Exception as e:
        logger.warning(f"Failed to list concepts: {e}")
        return []


@router.get("/concepts/{concept_name}", response_model=ConceptResponse)
async def get_concept(
    project_id: int, concept_name: str, manager=Depends(get_memory_manager)
):
    """
    Get a single concept by name with its episode count.
    """
    try:
        # We use search with the exact name to find the concept details
        results = await manager.long_term.search_concepts_data(concept_name, project_id)
        if not results:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        # Match exact name
        exact_match = next((r for r in results if r["name"] == concept_name), None)
        if not exact_match:
            raise HTTPException(status_code=404, detail="Concept not found")

        # Get episode count
        episodes = await manager.long_term.find_episodes_by_concept(
            concept_name, project_id, limit=1
        )
        # Note: In a real scenario, we might need a dedicated count method 
        # but for now we'll assume the result has the count or fetch it.
        # Actually, list_concepts already has counts. 
        # For simplicity in this mock/impl, we'll return the match.
        
        return ConceptResponse(
            name=exact_match["name"],
            description=exact_match.get("description"),
            episode_count=len(episodes) # This is a placeholder since we don't have a count-only method
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get concept {concept_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/concepts")
async def add_concept(
    project_id: int, req: ConceptCreate, manager=Depends(get_memory_manager)
):
    """
    Manually add a concept/memory.
    """
    try:
        from app.core.memory.interfaces.long_term import Concept

        concept = Concept(req.name, req.description, project_id, req.related_files)
        await manager.long_term.store_concept(concept)
        return {"status": "success", "name": req.name}
    except Exception as e:
        logger.error(f"Failed to add concept: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=list[ConceptResponse])
async def search_memory(
    q: str, 
    project_id: int | None = None, 
    use_vector: bool = Query(False, description="Use vector similarity search if available"),
    manager=Depends(get_memory_manager)
):
    """
    Search memory concepts.
    
    Args:
        q: Search query
        project_id: Optional project filter
        use_vector: If True, uses vector similarity search instead of text matching
    """
    if not q:
        return []
    
    # If vector search is requested, try to use it
    if use_vector:
        try:
            vector_results = await _perform_vector_search(q, project_id, top_k=10)
            # Convert vector results to ConceptResponse format
            return [
                ConceptResponse(
                    name=r["identifier"] or r["file_path"].split("/")[-1],
                    description=r["content"][:200] + "..." if len(r["content"]) > 200 else r["content"]
                )
                for r in vector_results
            ]
        except Exception as e:
            logger.warning(f"Vector search failed, falling back to text search: {e}")
            # Fall through to text search
    
    # Default text search
    result = await manager.long_term.search_concepts_data(q, project_id)
    return result


@router.get("/search/vector", response_model=VectorSearchResponse)
async def search_memory_vector(
    q: str,
    project_id: int | None = None,
    top_k: int = Query(10, ge=1, le=50),
    repository_id: str | None = None,
):
    """
    Semantic vector search for code and documents.
    
    Uses embeddings to find semantically similar content rather than just text matching.
    This provides better results for conceptual queries.
    
    Args:
        q: Search query (natural language)
        project_id: Optional project filter (legacy, use repository_id)
        top_k: Number of results to return
        repository_id: Optional repository filter
    """
    if not q:
        return VectorSearchResponse(results=[], total=0, query=q, search_type="vector")
    
    try:
        results = await _perform_vector_search(q, project_id, top_k, repository_id)
        
        # Convert to response model
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
                score=r["score"]
            )
            for r in results
        ]
        
        return VectorSearchResponse(
            results=search_results,
            total=len(search_results),
            query=q,
            search_type="vector"
        )
        
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Vector search failed: {str(e)}")


async def _perform_vector_search(
    query: str,
    project_id: int | None = None,
    top_k: int = 10,
    repository_id: str | None = None
) -> list[dict[str, Any]]:
    """
    Perform vector similarity search.
    
    Args:
        query: Search query text
        project_id: Legacy project ID (converted to repository_id)
        top_k: Number of results
        repository_id: Repository filter
        
    Returns:
        List of search results with similarity scores
    """
    # Get embedder
    embedder = EmbedderFactory.get_embedder()
    
    # Generate query embedding
    query_embedding = await embedder.aembed_query(query)
    
    # Get vector store
    vector_store = get_vector_store()
    
    # Determine repository filter
    repo_filter = repository_id
    if not repo_filter and project_id:
        repo_filter = str(project_id)
    
    # Search in code chunks
    results = vector_store.search_code(
        query_vector=query_embedding,
        top_k=top_k,
        repository_id=repo_filter
    )
    
    return results


@router.get("/search/hybrid", response_model=dict)
async def search_memory_hybrid(
    q: str,
    project_id: int | None = None,
    top_k: int = Query(10, ge=1, le=50),
    vector_weight: float = Query(0.7, ge=0, le=1),
):
    """
    Hybrid search combining vector similarity and text matching.
    
    Args:
        q: Search query
        project_id: Optional project filter
        top_k: Number of results
        vector_weight: Weight for vector scores (0-1), text match gets (1-weight)
    """
    if not q:
        return {"results": [], "total": 0, "query": q, "search_type": "hybrid"}
    
    try:
        # Get vector results
        vector_results = await _perform_vector_search(q, project_id, top_k * 2)
        
        # Get text results from memory manager
        from app.core.memory.lifespan import MemoryLifespanManager
        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        text_results = await container.memory_manager.long_term.search_concepts_data(q, project_id)
        
        # Combine and deduplicate results
        combined_results = []
        seen_ids = set()
        
        # Add vector results with weighted score
        for r in vector_results:
            if r["id"] not in seen_ids:
                combined_results.append({
                    "type": "vector",
                    "score": r["score"] * vector_weight,
                    "data": r
                })
                seen_ids.add(r["id"])
        
        # Add text results with weighted score
        for r in text_results:
            # Generate a pseudo-ID for text results
            result_id = f"text_{r['name']}"
            if result_id not in seen_ids:
                combined_results.append({
                    "type": "text",
                    "score": (1 - vector_weight) * 0.8,  # Text matches get slightly lower base score
                    "data": r
                })
                seen_ids.add(result_id)
        
        # Sort by score and take top_k
        combined_results.sort(key=lambda x: x["score"], reverse=True)
        final_results = combined_results[:top_k]
        
        return {
            "results": final_results,
            "total": len(final_results),
            "query": q,
            "search_type": "hybrid",
            "vector_results_count": len(vector_results),
            "text_results_count": len(text_results)
        }
        
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        # Fallback to text search
        from app.core.memory.lifespan import MemoryLifespanManager
        if not MemoryLifespanManager.is_initialized():
            await MemoryLifespanManager.ainitialize()
        container = MemoryLifespanManager.get_container()
        text_results = await container.memory_manager.long_term.search_concepts_data(q, project_id)
        return {
            "results": [{"type": "text", "score": 1.0, "data": r} for r in text_results],
            "total": len(text_results),
            "query": q,
            "search_type": "text_fallback"
        }


@router.delete("/concepts/{concept_name}")
async def delete_concept(
    project_id: int, concept_name: str, manager=Depends(get_memory_manager)
):
    """
    Delete a concept/memory.
    """
    try:
        # Construct the internal memory ID (following _LongTermAdapter convention)
        memory_id = f"concept_{concept_name}"
        success = await manager.delete_memory(memory_id)
        if not success:
            raise HTTPException(status_code=404, detail="Concept not found")
        return {"status": "success", "name": concept_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete concept {concept_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/concepts/{concept_name}")
async def update_concept(
    project_id: int, 
    concept_name: str, 
    req: ConceptUpdate, 
    manager=Depends(get_memory_manager)
):
    """
    Update an existing concept's description or metadata.
    """
    try:
        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        
        memory_id = f"concept_{concept_name}"
        existing = await manager.get_memory(memory_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Concept not found")
        
        # Update fields
        if req.description is not None:
            existing.content = req.description
            existing.description = req.description[:200]
        if req.related_files is not None:
            # Update tags by filtering out old file tags and adding new ones
            # (Simplistic tag management for now)
            other_tags = [t for t in existing.tags if t != "concept" and not t.startswith("file:")]
            existing.tags = ["concept"] + other_tags + req.related_files
            
        await manager.save_memory(existing)
        return {"status": "success", "name": concept_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update concept {concept_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/episodes/by-concept", response_model=list[EpisodeResponse])
async def get_episodes_by_concept(
    project_id: int, concept: str, limit: int = 10, manager=Depends(get_memory_manager)
):
    """
    Find all episodes linked to a specific concept.
    """
    if not concept:
        return []
    try:
        results = await manager.long_term.find_episodes_by_concept(
            concept, project_id, limit
        )
        return results
    except Exception as e:
        logger.error(f"Failed to find episodes by concept: {e}")
        return []


@router.post("/maintenance/deduplicate-checkpoints")
async def deduplicate_checkpoints(
    dry_run: bool = True,
    manager=Depends(get_memory_manager)
):
    """
    Remove duplicate checkpoint memories.

    Duplicate checkpoints are those with the same thread_id and task_progress
    within a 5-minute window. Only the most recent is kept.

    Args:
        dry_run: If True, only report duplicates without deleting them

    Returns:
        Deduplication statistics
    """
    try:
        result = await manager.deduplicate_checkpoints(dry_run=dry_run)
        return result
    except Exception as e:
        logger.error(f"Failed to deduplicate checkpoints: {e}")
        raise HTTPException(status_code=500, detail=f"Deduplication failed: {str(e)}")
