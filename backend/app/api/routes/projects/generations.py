"""Generation artifact API routes for projects."""

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.deps import TokenDep
from app.api.schemas.projects import (
    GenerationContentResponse,
    GenerationDispatchResponse,
    GenerationItemRequest,
    GenerationRetryRequest,
    GenerationStatusRecord,
    GenerationStatusResponse,
)
from app.domain.codebase.constants import GENERATION_ITEMS
from app.domain.codebase.generation.runner import run_generation_item
from app.domain.codebase.generation.scheduler import (
    dispatch_generation,
    get_generation_content,
    list_generation_status,
    retry_generation_item,
)

router = APIRouter(prefix="", tags=["generations"])


@router.post("/{project_id}/generations", response_model=GenerationDispatchResponse)
async def dispatch_generation_endpoint(
    project_id: int,
    req: GenerationItemRequest,
    bg_tasks: BackgroundTasks,
    _token: TokenDep,
):
    """Dispatch one or more generation artifacts (wiki, appmap, summary).

    Each dispatched artifact runs as a background Agent task.
    Project profile / PROJECT.md is not handled here; use the existing
    ``/api/v1/projects/{project_id}/profile/discover`` endpoint.
    """
    if req.project_id != project_id:
        raise HTTPException(status_code=400, detail="project_id mismatch")

    result = await dispatch_generation(project_id, req.artifact_names)
    for item in result.get("dispatched", []):
        bg_tasks.add_task(run_generation_item, project_id, item)
    return GenerationDispatchResponse(
        status="success",
        project_id=project_id,
        dispatched=result.get("dispatched", []),
        records={
            item: GenerationStatusRecord(**record)
            for item, record in result.get("items", {}).items()
        },
    )


@router.get("/{project_id}/generations", response_model=GenerationStatusResponse)
async def list_generation_status_endpoint(project_id: int, _token: TokenDep):
    """List status for all generation artifacts of a project."""
    records = await list_generation_status(project_id)
    return GenerationStatusResponse(
        status="success",
        project_id=project_id,
        records=[GenerationStatusRecord(**record) for record in records],
    )


@router.post("/{project_id}/generations/{item}/retry", response_model=GenerationStatusResponse)
async def retry_generation_endpoint(
    project_id: int,
    item: str,
    req: GenerationRetryRequest,
    _token: TokenDep,
):
    """Retry a failed generation artifact."""
    if req.project_id != project_id or req.artifact_name != item:
        raise HTTPException(status_code=400, detail="project_id or item mismatch")

    result = await retry_generation_item(project_id, item)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    records = await list_generation_status(project_id)
    return GenerationStatusResponse(
        status="success",
        project_id=project_id,
        records=[GenerationStatusRecord(**i) for i in records],
    )


@router.get("/{project_id}/generations/{item}/content", response_model=GenerationContentResponse)
async def get_generation_content_endpoint(project_id: int, item: str, _token: TokenDep):
    """Get the final generated content for a single artifact."""
    if item not in GENERATION_ITEMS:
        raise HTTPException(status_code=400, detail=f"Unknown item: {item}")

    result = await get_generation_content(project_id, item)
    return GenerationContentResponse(
        status="success",
        project_id=project_id,
        item=item,
        content=result.get("content"),
        content_type=result.get("content_type", "markdown"),
    )
