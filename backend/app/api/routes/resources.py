import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.schemas.resources import ResourceCreate, ResourceResponse, OperationResponse
from app.infrastructure.database.sql.database import get_db_session
from app.models import ProjectResource

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_id}/resources", tags=["resources"])

@router.get("", response_model=list[ResourceResponse])
async def list_resources(project_id: int):
    """List all pinned resources for a project."""
    try:
        async with get_db_session() as session:
            stmt = select(ProjectResource).where(ProjectResource.project_id == project_id).order_by(ProjectResource.created_at.desc())
            result = await session.execute(stmt)
            resources = result.scalars().all()
            return [
                ResourceResponse(
                    id=r.id,
                    project_id=r.project_id,
                    type=r.type,
                    name=r.name,
                    content=r.content,
                    created_at=r.created_at.isoformat(),
                )
                for r in resources
            ]
    except Exception as e:
        logger.error(f"Failed to list resources: {e}")
        return []

@router.post("", response_model=ResourceResponse)
async def create_resource(project_id: int, req: ResourceCreate):
    """Add a new resource (Pin a file or add a link)."""
    try:
        async with get_db_session() as session:
            # Idempotency check for files: don't double pin
            if req.type == "file":
                stmt = select(ProjectResource).where(
                    ProjectResource.project_id == project_id,
                    ProjectResource.type == "file",
                    ProjectResource.content == req.content,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                if existing:
                    # Update name if changed? Or just return existing
                    return ResourceResponse(
                        id=existing.id,
                        project_id=existing.project_id,
                        type=existing.type,
                        name=existing.name,
                        content=existing.content,
                        created_at=existing.created_at.isoformat(),
                    )

            resource = ProjectResource(
                project_id=project_id,
                type=req.type,
                name=req.name,
                content=req.content
            )
            session.add(resource)
            await session.commit()
            await session.refresh(resource)

            return ResourceResponse(
                id=resource.id,
                project_id=resource.project_id,
                type=resource.type,
                name=resource.name,
                content=resource.content,
                created_at=resource.created_at.isoformat(),
            )
    except Exception as e:
        logger.error(f"Failed to create resource: {e}")
        raise HTTPException(500, str(e))

@router.delete("/{resource_id}", response_model=OperationResponse)
async def delete_resource(project_id: int, resource_id: int):
    """Remove a resource."""
    try:
        async with get_db_session() as session:
            resource = await session.get(ProjectResource, resource_id)
            if not resource:
                # Silent success if already gone
                return OperationResponse(status="success", id=resource_id)

            if resource.project_id != project_id:
                raise HTTPException(403, "Resource access denied")

            await session.delete(resource)
            return OperationResponse(status="success", id=resource_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete resource: {e}")
        raise HTTPException(500, str(e))
