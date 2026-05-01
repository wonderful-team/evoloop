import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas.memory import ConceptCreate, ConceptUpdate, ConceptResponse, EpisodeResponse, VectorSearchResult, \
    VectorSearchResponse, HybridResultItem, HybridSearchResponse, ConceptOperationResponse
from app.core.memory.models import MemoryType
from app.infrastructure.database.vector import get_vector_store
from app.infrastructure.embeddings.factory import EmbedderFactory

logger = logging.getLogger(__name__)

router = APIRouter(tags=["memory"])

async def get_memory_manager():
    """Dependency to get memory manager via MemoryLifespanManager (singleton)."""
    from app.core.memory.lifespan import MemoryLifespanManager

    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()

    yield MemoryLifespanManager.get_manager()

@router.get("/concepts", response_model=list[ConceptResponse])
async def list_concepts(project_id: int, manager=Depends(get_memory_manager)):
    """
    Get all concepts for a project.
    """
    try:
        # Use storage-level project filtering
        results = await manager.list_memories(
            type_filter=MemoryType.CONCEPT, 
            project_id=project_id,
            limit=100
        )
        # Get counts in batch
        counts = await manager.get_concept_episode_counts_batch(project_id)
        
        return [
            ConceptResponse(
                name=m.title,
                description=m.description,
                episode_count=counts.get(m.title, 0)
            ) for m in results
        ]
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
        # Use storage-level project filtering
        results = await manager.list_memories(
            type_filter=MemoryType.CONCEPT, 
            project_id=project_id,
            limit=limit
        )
        # Get counts in batch
        counts = await manager.get_concept_episode_counts_batch(project_id)

        return [
            ConceptResponse(
                name=m.title,
                description=m.description,
                episode_count=counts.get(m.title, 0)
            ) for m in results
        ]
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
        # Construct ID
        memory_id = f"concept_{concept_name}"
        entry = await manager.get_memory(memory_id)
        
        if not entry:
            raise HTTPException(status_code=404, detail="Concept not found")

        # Get episode count
        episodes = await manager.find_episodes_by_concept(
            concept_name, project_id, limit=99
        )
        
        return ConceptResponse(
            name=entry.title,
            description=entry.content,
            episode_count=len(episodes)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get concept {concept_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/concepts", response_model=ConceptOperationResponse)
async def add_concept(
    project_id: int, req: ConceptCreate, manager=Depends(get_memory_manager)
):
    """
    Manually add a concept/memory.
    """
    try:
        await manager.store_concept(
            name=req.name,
            description=req.description,
            project_id=project_id,
            related_files=req.related_files
        )
        return ConceptOperationResponse(status="success", name=req.name)
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
    
    TODO: `use_vector` is accepted for API compatibility but not yet implemented
    in the backend search logic.
    """
    if not q:
        return []
    
    if not q:
        return []
    
    # Text search (unified)
    results = await manager.search_memories(
        query=q,
        types=[MemoryType.CONCEPT],
        project_id=project_id,
        limit=10,
    )
    return [
        ConceptResponse(
            name=r.title,
            description=r.description,
            episode_count=0
        ) for r in results
    ]

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
    
    # Search in code chunks (run sync I/O in thread to avoid blocking)
    results = await asyncio.to_thread(
        vector_store.search_code,
        query_vector=query_embedding,
        top_k=top_k,
        repository_id=repo_filter
    )
    
    return results

@router.get("/search/hybrid", response_model=HybridSearchResponse)
async def search_memory_hybrid(
    q: str,
    project_id: int | None = None,
    top_k: int = Query(10, ge=1, le=50),
    vector_weight: float = Query(0.7, ge=0, le=1),
    manager=Depends(get_memory_manager)
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
        return HybridSearchResponse(results=[], total=0, query=q or "", search_type="hybrid")
    
    try:
        # Get vector results
        vector_results = await _perform_vector_search(q, project_id, top_k * 2)
        
        # Get text results from memory manager
        results = await manager.search_memories(
            query=q,
            types=[MemoryType.CONCEPT],
            project_id=project_id,
            limit=top_k,
        )
        text_results = [
            {"name": r.title, "description": r.description} for r in results
        ]
        
        # Combine and deduplicate results
        combined_results = []
        seen_ids = set()
        
        # Add vector results with weighted score
        for r in vector_results:
            if r["id"] not in seen_ids:
                combined_results.append(HybridResultItem(
                    type="vector",
                    score=r["score"] * vector_weight,
                    data=r
                ))
                seen_ids.add(r["id"])
        
        # Add text results with weighted score
        for r in text_results:
            # Generate a pseudo-ID for text results
            result_id = f"text_{r['name']}"
            if result_id not in seen_ids:
                combined_results.append(HybridResultItem(
                    type="text",
                    score=(1 - vector_weight) * 0.8,  # Text matches get slightly lower base score
                    data=r
                ))
                seen_ids.add(result_id)
        
        # Sort by score and take top_k
        combined_results.sort(key=lambda x: x["score"], reverse=True)
        final_results = combined_results[:top_k]
        
        return HybridSearchResponse(
            results=final_results,
            total=len(final_results),
            query=q,
            search_type="hybrid",
            vector_results_count=len(vector_results),
            text_results_count=len(text_results)
        )
        
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        # Fallback to text search via facade
        text_results = await manager.search_concepts_data(q, project_id)
        return HybridSearchResponse(
            results=[HybridResultItem(type="text", score=1.0, data=r) for r in text_results],
            total=len(text_results),
            query=q,
            search_type="text_fallback"
        )

@router.delete("/concepts/{concept_name}", response_model=ConceptOperationResponse)
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
        return ConceptOperationResponse(status="success", name=concept_name)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete concept {concept_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/concepts/{concept_name}", response_model=ConceptOperationResponse)
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
            other_tags = [t for t in existing.tags if t != "concept" and not t.endswith(".py") and not t.endswith(".ts")]
            existing.tags = ["concept"] + other_tags + req.related_files
            
        await manager.save_memory(existing)
        return ConceptOperationResponse(status="success", name=concept_name)
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
        results = await manager.find_episodes_by_concept(
            concept, project_id, limit
        )
        # results are already dicts matching EpisodeResponse mostly
        return [
            EpisodeResponse(
                id=r['id'],
                goal=r['goal'],
                result=r['result'],
                error=None,
                timestamp=r['timestamp']
            ) for r in results
        ]
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
