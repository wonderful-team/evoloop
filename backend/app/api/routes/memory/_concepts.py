import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUserOptional
from app.api.schemas.memory import (
    ConceptCreate,
    ConceptOperationResponse,
    ConceptResponse,
    ConceptUpdate,
)
from app.core.memory.models import MemoryType

from ._shared import get_memory_manager

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/concepts", response_model=list[ConceptResponse])
async def list_concepts(
    project_id: int,
    manager=Depends(get_memory_manager),
    current_user: CurrentUserOptional = None,
):
    try:
        results = await manager.list_memories(
            type_filter=MemoryType.CONCEPT,
            project_id=project_id,
            limit=100,
            member_id=current_user.id if current_user else 0,
        )
        counts = await manager.get_concept_episode_counts_batch(
            project_id, member_id=current_user.id if current_user else 0
        )

        return [
            ConceptResponse(
                name=m.title,
                description=m.description,
                episode_count=counts.get(m.title, 0),
            )
            for m in results
        ]
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Failed to list concepts: {e}")
        return []


@router.get("/mobile/concepts")
async def list_concepts_for_mobile(
    project_id: int,
    manager=Depends(get_memory_manager),
    current_user: CurrentUserOptional = None,
):
    results = await manager.list_memories(
        type_filter=MemoryType.CONCEPT,
        project_id=project_id,
        limit=100,
        member_id=current_user.id if current_user else 0,
    )
    return [
        {
            "id": m.id,
            "name": m.title,
            "description": m.description,
            "related_files": [],
            "created_at": m.created_at.isoformat() if m.created_at else "",
        }
        for m in results
    ]


@router.get("/concepts/list", response_model=list[ConceptResponse])
async def list_concepts_with_counts(
    project_id: int | None = None,
    limit: int = 50,
    manager=Depends(get_memory_manager),
    current_user: CurrentUserOptional = None,
):
    try:
        results = await manager.list_memories(
            type_filter=MemoryType.CONCEPT,
            project_id=project_id,
            limit=limit,
            member_id=current_user.id if current_user else 0,
        )
        counts = await manager.get_concept_episode_counts_batch(
            project_id, member_id=current_user.id if current_user else 0
        )

        return [
            ConceptResponse(
                name=m.title,
                description=m.description,
                episode_count=counts.get(m.title, 0),
            )
            for m in results
        ]
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.warning(f"Failed to list concepts: {e}")
        return []


@router.get("/concepts/{concept_name}", response_model=ConceptResponse)
async def get_concept(
    project_id: int,
    concept_name: str,
    manager=Depends(get_memory_manager),
    current_user: CurrentUserOptional = None,
):
    try:
        memory_id = f"concept_{concept_name.lower().replace(' ', '_')}"
        entry = await manager.get_memory(memory_id)

        if not entry:
            raise HTTPException(status_code=404, detail="Concept not found")

        episodes = await manager.find_episodes_by_concept(
            concept_name,
            project_id,
            limit=99,
            member_id=current_user.id if current_user else 0,
        )

        return ConceptResponse(
            name=entry.title, description=entry.content, episode_count=len(episodes)
        )
    except HTTPException:
        raise
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Failed to get concept {concept_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/concepts", response_model=ConceptOperationResponse)
async def add_concept(
    project_id: int,
    req: ConceptCreate,
    manager=Depends(get_memory_manager),
    current_user: CurrentUserOptional = None,
):
    try:
        await manager.store_concept(
            concept=req.name,
            description=req.description,
            project_id=project_id,
            related_files=req.related_files,
            member_id=current_user.id if current_user else 0,
            source_message_id=req.source_message_id,
            source_thread_id=req.source_thread_id,
            created_by_member_id=req.created_by_member_id or (current_user.id if current_user else 0),
            memory_kind=req.memory_kind,
        )
        return ConceptOperationResponse(status="success", name=req.name)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Failed to add concept: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/concepts/{concept_name}", response_model=ConceptOperationResponse)
async def delete_concept(
    _project_id: int,
    concept_name: str,
    manager=Depends(get_memory_manager),
    _current_user: CurrentUserOptional = None,
):
    try:
        memory_id = f"concept_{concept_name.lower().replace(' ', '_')}"
        success = await manager.delete_memory(memory_id)
        if not success:
            raise HTTPException(status_code=404, detail="Concept not found")
        return ConceptOperationResponse(status="success", name=concept_name)
    except HTTPException:
        raise
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Failed to delete concept {concept_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/concepts/{concept_name}", response_model=ConceptOperationResponse)
async def update_concept(
    _project_id: int,
    concept_name: str,
    req: ConceptUpdate,
    manager=Depends(get_memory_manager),
    _current_user: CurrentUserOptional = None,
):
    try:
        memory_id = f"concept_{concept_name.lower().replace(' ', '_')}"
        existing = await manager.get_memory(memory_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Concept not found")

        if req.description is not None:
            existing.content = req.description
            existing.description = req.description[:200]
        if req.related_files is not None:
            other_tags = [
                t
                for t in existing.tags
                if t != "concept" and not t.endswith(".py") and not t.endswith(".ts")
            ]
            existing.tags = ["concept"] + other_tags + req.related_files

        await manager.save_memory(existing)
        return ConceptOperationResponse(status="success", name=concept_name)
    except HTTPException:
        raise
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error(f"Failed to update concept {concept_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
