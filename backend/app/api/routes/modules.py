"""API routes for module graph data."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import TokenDep
from app.domain.codebase.generation.module_graph import module_graph_service

router = APIRouter(tags=["modules"])


@router.get("/projects/{project_id}/modules")
async def list_modules(
    project_id: int,
    _token: TokenDep,
):
    modules = await module_graph_service.get_modules(project_id)
    return [
        {
            "name": m.name,
            "entities": m.entities,
            "entity_count": m.entity_count,
            "summary": m.summary,
        }
        for m in modules
    ]


@router.get("/projects/{project_id}/modules/{entity}")
async def get_module_of(
    project_id: int,
    entity: str,
    _token: TokenDep,
):
    module_name = await module_graph_service.get_module_of(project_id, entity)
    return {"entity": entity, "module": module_name}
