"""
Project import management endpoints — scan, detect, import, ignore, unignore, batch.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUserOptional, TokenDep, TokenDepOptional
from app.api.responses import ListResponse
from app.api.schemas.projects import (
    BatchImportRequest,
    BatchImportResponse,
    BatchResultItem,
    DetectedProjectItem,
    IgnoreProjectResponse,
    ImportProjectResponse,
    UnignoreProjectResponse,
)
from app.core.project.sync_service import project_sync_service
from app.core.project.utils import get_project_path
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/scan", response_model=ListResponse[DetectedProjectItem])
async def scan_workspace_projects_endpoint(_token: TokenDep):
    workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
    if not workspace_root:
        raise HTTPException(400, "WORKSPACE_ROOT not configured. Please set it in Settings.")

    try:
        await project_sync_service.reconcile_projects(workspace_root, force=True)
        repos = await project_sync_service.get_detected_projects()
        return ListResponse[DetectedProjectItem](
            data=[
                DetectedProjectItem(
                    id=r.id,
                    name=r.name,
                    path=await get_project_path(r.project_id) if r.project_id else r.local_path,
                    detected_at=r.detected_at.isoformat() if r.detected_at else None,
                )
                for r in repos
            ]
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error("Failed to scan workspace: %s", e)
        raise HTTPException(500, f"Scan failed: {str(e)}")


@router.get("/detected", response_model=ListResponse[DetectedProjectItem])
async def get_detected_projects(
    force: bool = False,
    _token: TokenDepOptional = None,
    current_user: CurrentUserOptional = None,
):
    if not force:
        config_value = SystemConfigService.get_value("PROJECT_DISCOVERY_ENABLED")
        if config_value is not None and config_value.lower() not in ("true", "1", "yes", "on"):
            logger.debug("[ProjectsAPI] Project discovery disabled by system config, returning empty detected list")
            return {"data": []}

    try:
        member_id = current_user.id if current_user else None
        repos = await project_sync_service.get_detected_projects(member_id=member_id)
        return ListResponse[DetectedProjectItem](
            data=[
                DetectedProjectItem(
                    id=r.id,
                    name=r.name,
                    path=await get_project_path(r.project_id) if r.project_id else r.local_path,
                    detected_at=r.detected_at.isoformat() if r.detected_at else None,
                )
                for r in repos
            ]
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error("Failed to get detected projects: %s", e)
        raise HTTPException(500, f"Failed to get detected projects: {str(e)}")


@router.post("/{repo_id}/import", response_model=ImportProjectResponse)
async def import_detected_project(repo_id: int, _token: TokenDep):
    try:
        repo = await project_sync_service.import_project(repo_id)
        return ImportProjectResponse(
            status="success",
            repo_id=repo.id,
            name=repo.name,
            message=f"Project '{repo.name}' imported successfully",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error("Failed to import project %d: %s", repo_id, e)
        raise HTTPException(500, f"Failed to import project: {str(e)}")


@router.post("/{repo_id}/ignore", response_model=IgnoreProjectResponse)
async def ignore_detected_project(repo_id: int, _token: TokenDep):
    try:
        await project_sync_service.ignore_project(repo_id)
        return IgnoreProjectResponse(status="ignored", repo_id=repo_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error("Failed to ignore project %d: %s", repo_id, e)
        raise HTTPException(500, f"Failed to ignore project: {str(e)}")


@router.get("/ignored", response_model=ListResponse[DetectedProjectItem])
async def get_ignored_projects(
    _token: TokenDep,
    current_user: CurrentUserOptional = None,
):
    try:
        member_id = current_user.id if current_user else None
        repos = await project_sync_service.get_ignored_projects(member_id=member_id)
        return ListResponse[DetectedProjectItem](
            data=[
                DetectedProjectItem(
                    id=r.id,
                    name=r.name,
                    path=await get_project_path(r.project_id) if r.project_id else r.local_path,
                    detected_at=r.detected_at.isoformat() if r.detected_at else None,
                )
                for r in repos
            ]
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error("Failed to get ignored projects: %s", e)
        raise HTTPException(500, f"Failed to get ignored projects: {str(e)}")


@router.post("/{repo_id}/unignore", response_model=UnignoreProjectResponse)
async def unignore_project(repo_id: int, _token: TokenDep):
    try:
        repo = await project_sync_service.unignore_project(repo_id)
        return UnignoreProjectResponse(
            status="restored",
            repo_id=repo.id,
            name=repo.name,
            message=f"Project '{repo.name}' restored to detected state",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
        logger.error("Failed to unignore project %d: %s", repo_id, e)
        raise HTTPException(500, f"Failed to restore project: {str(e)}")


@router.post("/batch/import", response_model=BatchImportResponse)
async def batch_import_projects(req: BatchImportRequest, _token: TokenDep):
    results: dict[str, list[BatchResultItem]] = {"success": [], "failed": []}
    for repo_id in req.repo_ids:
        try:
            repo = await project_sync_service.import_project(repo_id)
            results["success"].append(BatchResultItem(repo_id=repo.id, name=repo.name))
        except ValueError as e:
            results["failed"].append(BatchResultItem(repo_id=repo_id, error=str(e)))
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error("Failed to import project %d: %s", repo_id, e)
            results["failed"].append(BatchResultItem(repo_id=repo_id, error=str(e)))

    return BatchImportResponse(
        status="completed",
        summary=f"Imported {len(results['success'])} of {len(req.repo_ids)} projects",
        results=results,
    )


@router.post("/batch/ignore", response_model=BatchImportResponse)
async def batch_ignore_projects(req: BatchImportRequest, _token: TokenDep):
    results: dict[str, list[BatchResultItem]] = {"success": [], "failed": []}
    for repo_id in req.repo_ids:
        try:
            await project_sync_service.ignore_project(repo_id)
            results["success"].append(BatchResultItem(repo_id=repo_id))
        except ValueError as e:
            results["failed"].append(BatchResultItem(repo_id=repo_id, error=str(e)))
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error("Failed to ignore project %d: %s", repo_id, e)
            results["failed"].append(BatchResultItem(repo_id=repo_id, error=str(e)))

    return BatchImportResponse(
        status="completed",
        summary=f"Ignored {len(results['success'])} of {len(req.repo_ids)} projects",
        results=results,
    )
