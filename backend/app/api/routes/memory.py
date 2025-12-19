from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional

from app.domain.memory.service import memory_service
from app.logging import logger

router = APIRouter(tags=["memory"])

class ConceptCreate(BaseModel):
    name: str
    description: str
    related_files: Optional[List[str]] = None

class ConceptResponse(BaseModel):
    name: str
    description: str

@router.get("/concepts", response_model=List[ConceptResponse])
async def list_concepts(project_id: int):
    """
    Get all concepts for a project.
    """
    # Use empty query to list "all" (limit applied)
    try:
        results = await memory_service.search_concepts_data("", project_id)
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
        await memory_service.add_concept(req.name, req.description, project_id, req.related_files)
        return {"status": "success", "name": req.name}
    except Exception as e:
        logger.error(f"Failed to add concept: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search", response_model=List[ConceptResponse])
async def search_memory(project_id: int, q: str):
    """
    Search memory concepts.
    """
    if not q: return []
    result = await memory_service.search_concepts_data(q, project_id)
    return result
