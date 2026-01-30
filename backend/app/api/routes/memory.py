import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.memory import memory_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["memory"])


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
async def list_concepts(project_id: int):
    """
    Get all concepts for a project (legacy endpoint).
    """
    try:
        results = await memory_manager.long_term.search_concepts_data("", project_id)
        return results
    except Exception as e:
        logger.warning(f"Failed to list concepts: {e}")
        return []


@router.get("/concepts/list", response_model=list[ConceptWithEpisodeCount])
async def list_concepts_with_counts(project_id: int, limit: int = 50):
    """
    Get all concepts with episode counts.
    """
    try:
        results = await memory_manager.long_term.list_concepts(project_id, limit)
        return results
    except Exception as e:
        logger.warning(f"Failed to list concepts: {e}")
        return []


@router.post("/concepts")
async def add_concept(project_id: int, req: ConceptCreate):
    """
    Manually add a concept/memory.
    """
    try:
        from app.core.memory.interfaces.long_term import Concept
        concept = Concept(req.name, req.description, project_id, req.related_files)
        await memory_manager.long_term.store_concept(concept)
        return {"status": "success", "name": req.name}
    except Exception as e:
        logger.error(f"Failed to add concept: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=list[ConceptResponse])
async def search_memory(project_id: int, q: str):
    """
    Search memory concepts.
    """
    if not q:
        return []
    result = await memory_manager.long_term.search_concepts_data(q, project_id)
    return result


@router.get("/episodes/by-concept", response_model=list[EpisodeResponse])
async def get_episodes_by_concept(project_id: int, concept: str, limit: int = 10):
    """
    Find all episodes linked to a specific concept.
    """
    if not concept:
        return []
    try:
        results = await memory_manager.long_term.find_episodes_by_concept(concept, project_id, limit)
        return results
    except Exception as e:
        logger.error(f"Failed to find episodes by concept: {e}")
        return []
