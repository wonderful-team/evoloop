"""
Project Requirements API Routes

Handles requirement document upload, analysis, and task breakdown.
"""

import logging
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from sqlalchemy.orm import selectinload

from app.api.deps import TokenDep, TokenDepOptional
from app.api.responses import ListResponse
from app.api.schemas.project_requirements import RequirementUploadResponse, RequirementListItem, \
    RequirementAnalysisItem, RequirementDetailResponse, RequirementDeleteResponse, RequirementTaskItem, \
    RequirementMapping, RequirementTasksResponse, RequirementProgress, RequirementSyncProgressResponse
from app.core.config import settings
from app.core.engine.background_agent import run_agent_background
from app.core.file.document_reader import document_reader_service
from app.domain.project.requirements import ProjectRequirementDocument
from app.infrastructure.database.sql.database import session_scope
from app.utils import render_template
from app.utils.id import gen_uuid

logger = logging.getLogger(__name__)

router = APIRouter(tags=["project-requirements"])

def _get_upload_dir() -> Path:
    """Get upload directory for requirement documents."""
    upload_dir = Path(settings.UPLOAD_DIR or "/tmp/evoloop/uploads")
    upload_dir = upload_dir / "requirements"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir

def _guess_file_type(filename: str) -> str:
    """Guess MIME type from filename."""
    ext = Path(filename).suffix.lower()
    mime_types = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".md": "text/markdown",
        ".txt": "text/plain",
    }
    return mime_types.get(ext, "application/octet-stream")

async def _save_uploaded_file(file: UploadFile, file_id: str) -> str:
    """Save uploaded file to disk."""
    upload_dir = _get_upload_dir()
    safe_name = Path(file.filename or "unnamed").name
    file_path = upload_dir / f"{file_id}_{safe_name}"

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return str(file_path)

@router.post("/projects/{project_id}/requirements/upload", response_model=RequirementUploadResponse)
async def upload_requirement_document(
    project_id: int,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    _token: TokenDep,
):
    """
    Upload a requirement document and start Agent analysis.

    Flow:
    1. Save file to disk
    2. Extract content using DocumentReaderService
    3. Create DB record
    4. Start Agent thread for analysis → confirmation → breakdown → sync
    """
    try:
        # 1. Save file
        file_id = gen_uuid()
        file_path = await _save_uploaded_file(file, file_id)

        # 2. Extract content
        content = await document_reader_service.read_document(file_path)

        # 3. Create DB record
        async with session_scope() as session:
            doc = ProjectRequirementDocument(
                id=file_id,
                project_id=project_id,
                file_name=file.filename or "unnamed",
                file_path=file_path,
                file_type=_guess_file_type(file.filename or ""),
                file_size=os.path.getsize(file_path),
                raw_content=content,
                status="pending",
            )
            session.add(doc)

        # 4. Start Agent background task
        thread_id = f"proj-{project_id}-req-{file_id}"

        # 4. Trigger Unified Dispatcher
        from app.core.engine.dispatch import dispatch_agent_run

        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=render_template(
                "domain/project/requirement_analysis.prompt.j2",
                document_id=file_id,
                file_name=file.filename,
                project_id=project_id,
            ),
            project_id=project_id,
            goal_prefix="[Requirement Analysis] ",
        )

        if result.status == "failed":
            raise HTTPException(status_code=500, detail=result.error)

        background_tasks.add_task(run_agent_background, thread_id, result.inputs)

        return RequirementUploadResponse(
            document_id=file_id,
            thread_id=thread_id,
            status="analysis_started",
            message="文档上传成功，AI 分析已启动，请查看对话线程",
        )

    except Exception as e:
        logger.exception(f"Failed to upload requirement document: {e}")
        raise HTTPException(500, f"Failed to upload document: {e}")

@router.get("/projects/{project_id}/requirements", response_model=ListResponse[RequirementListItem])
async def list_project_requirements(
    project_id: int,
    _token: TokenDepOptional,
):
    """Get all requirement documents for a project."""
    from sqlalchemy import select

    async with session_scope() as session:
        stmt = (
            select(ProjectRequirementDocument)
            .where(ProjectRequirementDocument.project_id == project_id)
            .order_by(ProjectRequirementDocument.created_at.desc())
            .options(selectinload(ProjectRequirementDocument.analyses))
        )

        result = await session.execute(stmt)
        docs = result.scalars().all()

        return ListResponse[RequirementListItem](
            data=[
                RequirementListItem(
                    id=d.id,
                    file_name=d.file_name,
                    file_type=d.file_type,
                    status=d.status,
                    created_at=d.created_at.isoformat() if d.created_at else None,
                    analysis_count=len(d.analyses),
                )
                for d in docs
            ]
        )

@router.get("/projects/{project_id}/requirements/{doc_id}", response_model=RequirementDetailResponse)
async def get_requirement_detail(
    project_id: int,
    doc_id: str,
    _token: TokenDepOptional,
):
    """Get requirement document detail with analyses."""
    async with session_scope() as session:
        doc = await session.get(ProjectRequirementDocument, doc_id)

        if not doc or doc.project_id != project_id:
            raise HTTPException(404, "Document not found")

        return RequirementDetailResponse(
            id=doc.id,
            file_name=doc.file_name,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=doc.status,
            raw_content_preview=(
                doc.raw_content[:1000] if doc.raw_content else None
            ),
            created_at=doc.created_at.isoformat() if doc.created_at else None,
            updated_at=doc.updated_at.isoformat() if doc.updated_at else None,
            analyses=[
                RequirementAnalysisItem(
                    id=a.id,
                    status=a.status,
                    version=a.version,
                    data=a.analysis_data,
                    user_edited=a.user_edited,
                    confirmed_at=(
                        a.confirmed_at.isoformat() if a.confirmed_at else None
                    ),
                    tasks_count=len(a.tasks),
                    synced_tasks=sum(
                        1 for t in a.tasks if t.sync_status == "synced"
                    ),
                )
                for a in doc.analyses
            ],
        )

@router.delete("/projects/{project_id}/requirements/{doc_id}", response_model=RequirementDeleteResponse)
async def delete_requirement_document(
    project_id: int,
    doc_id: str,
    _token: TokenDep,
):
    """Delete a requirement document and all its analyses/tasks."""
    async with session_scope() as session:
        doc = await session.get(ProjectRequirementDocument, doc_id)

        if not doc or doc.project_id != project_id:
            raise HTTPException(404, "Document not found")

        # Delete file from disk
        try:
            if os.path.exists(doc.file_path):
                os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"Failed to delete file {doc.file_path}: {e}")

        # Delete DB record (cascade will delete analyses and tasks)
        await session.delete(doc)

        return RequirementDeleteResponse(status="deleted", document_id=doc_id)

@router.get("/projects/{project_id}/requirements/{doc_id}/analyses/{analysis_id}/tasks", response_model=RequirementTasksResponse)
async def get_analysis_tasks(
    project_id: int,
    doc_id: str,
    analysis_id: str,
    _token: TokenDepOptional,
):
    """
    Get all tasks for a specific analysis with their EvoCloud sync status.

    Returns task list with sync status breakdown for visualization.
    """
    from sqlalchemy import select
    from app.domain.project.requirements.models import (
        ProjectRequirementAnalysis,
        ProjectRequirementTask,
    )

    async with session_scope() as session:
        # Verify analysis exists and belongs to the project
        analysis = await session.get(ProjectRequirementAnalysis, analysis_id)
        if not analysis or analysis.project_id != project_id:
            raise HTTPException(404, "Analysis not found")

        # Verify document exists
        doc = await session.get(ProjectRequirementDocument, doc_id)
        if not doc or doc.project_id != project_id:
            raise HTTPException(404, "Document not found")

        # Get all tasks for this analysis
        stmt = (
            select(ProjectRequirementTask)
            .where(ProjectRequirementTask.analysis_id == analysis_id)
            .order_by(ProjectRequirementTask.created_at.asc())
        )
        result = await session.execute(stmt)
        tasks = result.scalars().all()

        # Calculate sync stats
        sync_stats = {
            "pending": 0,
            "syncing": 0,
            "synced": 0,
            "failed": 0,
            "total": len(tasks),
        }

        for task in tasks:
            sync_stats[task.sync_status] += 1

        return RequirementTasksResponse(
            analysis_id=analysis_id,
            document_id=doc_id,
            project_id=project_id,
            sync_stats=sync_stats,
            tasks=[
                RequirementTaskItem(
                    id=t.id,
                    title=t.task_data.get("title", "Untitled"),
                    description=t.task_data.get("description", ""),
                    priority=t.task_data.get("priority", "medium"),
                    estimated_hours=t.task_data.get("estimated_hours", 0),
                    category=t.task_data.get("category", "general"),
                    tags=t.task_data.get("tags", []),
                    requirement_refs=t.task_data.get("requirement_refs", []),
                    acceptance_criteria=t.task_data.get("acceptance_criteria", []),
                    sync_status=t.sync_status,
                    sync_error=t.sync_error,
                    evocloud_task_id=t.evocloud_task_id,
                    synced_at=t.synced_at.isoformat() if t.synced_at else None,
                    created_at=t.created_at.isoformat() if t.created_at else None,
                )
                for t in tasks
            ],
            requirement_mapping=RequirementMapping.model_validate(
                _build_requirement_mapping(tasks)
            ),
        )

def _build_requirement_mapping(tasks: list) -> dict:
    """Build a mapping of requirements to tasks for visualization."""
    mapping = {
        "by_requirement": {},  # req_ref -> [task_ids]
        "by_task": {},  # task_id -> [req_refs]
        "unmapped_tasks": [],  # tasks without requirement refs
    }

    for task in tasks:
        task_id = task.id
        refs = task.task_data.get("requirement_refs", [])

        if not refs:
            mapping["unmapped_tasks"].append(task_id)
            mapping["by_task"][task_id] = []
        else:
            mapping["by_task"][task_id] = refs
            for ref in refs:
                if ref not in mapping["by_requirement"]:
                    mapping["by_requirement"][ref] = []
                mapping["by_requirement"][ref].append(task_id)

    return mapping

@router.get("/projects/{project_id}/requirements/{doc_id}/analyses/{analysis_id}/sync-progress", response_model=RequirementSyncProgressResponse)
async def get_analysis_sync_progress(
    project_id: int,
    doc_id: str,
    analysis_id: str,
    _token: TokenDepOptional,
):
    """
    Get real-time sync progress for an analysis.

    Returns current sync status and progress percentage.
    """
    from sqlalchemy import select, func
    from app.domain.project.requirements.models import (
        ProjectRequirementAnalysis,
        ProjectRequirementTask,
    )

    async with session_scope() as session:
        # Verify analysis exists
        analysis = await session.get(ProjectRequirementAnalysis, analysis_id)
        if not analysis or analysis.project_id != project_id:
            raise HTTPException(404, "Analysis not found")

        # Get sync stats
        stmt = (
            select(
                ProjectRequirementTask.sync_status,
                func.count().label("count")
            )
            .where(ProjectRequirementTask.analysis_id == analysis_id)
            .group_by(ProjectRequirementTask.sync_status)
        )
        result = await session.execute(stmt)
        rows = result.all()

        stats = {row.sync_status: row.count for row in rows}
        total = sum(stats.values())

        synced = stats.get("synced", 0)
        failed = stats.get("failed", 0)
        syncing = stats.get("syncing", 0)
        pending = stats.get("pending", 0)

        # Calculate progress
        progress = RequirementProgress(
            total=total,
            synced=synced,
            failed=failed,
            syncing=syncing,
            pending=pending,
            percentage=round((synced / total * 100), 1) if total > 0 else 0,
            is_complete=pending == 0 and syncing == 0,
            has_failures=failed > 0,
        )

        return RequirementSyncProgressResponse(
            analysis_id=analysis_id,
            progress=progress,
            last_updated=analysis.confirmed_at.isoformat() if analysis.confirmed_at else None,
        )