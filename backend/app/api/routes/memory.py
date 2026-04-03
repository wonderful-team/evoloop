import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.memory import MemoryContainer, MemoryConfig

logger = logging.getLogger(__name__)

router = APIRouter(tags=["memory"])


async def get_memory_manager():
    """Dependency to get memory manager with proper initialization and cleanup."""
    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    try:
        yield container.memory_manager
    finally:
        await container.shutdown()


class ConceptCreate(BaseModel):
    name: str
    description: str
    related_files: list[str] | None = None


class ConceptResponse(BaseModel):
    name: str
    description: str


class ConceptWithEpisodeCount(BaseModel):
    name: str
    description: str | None
    episode_count: int


class EpisodeResponse(BaseModel):
    id: str
    goal: str
    result: str | None
    error: str | None
    timestamp: int | None


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


@router.get("/concepts/list", response_model=list[ConceptWithEpisodeCount])
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
    q: str, project_id: int | None = None, manager=Depends(get_memory_manager)
):
    """
    Search memory concepts.
    """
    if not q:
        return []
    result = await manager.long_term.search_concepts_data(q, project_id)
    return result


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
