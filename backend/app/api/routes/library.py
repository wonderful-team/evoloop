import logging
import os
import shutil
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.config import settings
from app.domain.codebase.indexing.service import IndexingService
from app.infrastructure.database.sql.database import get_db
from app.models import Repository, SourceFile, User

logger = logging.getLogger(__name__)

router = APIRouter()


async def get_library_repo(db: AsyncSession) -> Repository:
    """Ensure the global library repository exists and return it."""
    indexing_service = IndexingService()
    # Path is settings.LIBRARY_ROOT, name is "Global Library", project_id=0
    repo = await indexing_service.get_or_create_repo(
        path=settings.LIBRARY_ROOT,
        name="Global Library",
        project_id=0
    )
    return repo


@router.get("/files")
async def list_library_files(
    db: AsyncSession = Depends(get_db),
    current_user: User = CurrentUser,
) -> list[dict[str, Any]]:
    """List all files in the global knowledge base."""
    repo = await get_library_repo(db)

    stmt = select(SourceFile).where(SourceFile.repository_id == repo.id)
    result = await db.execute(stmt)
    files = result.scalars().all()

    return [
        {
            "id": f.id,
            "path": f.path,
            "name": os.path.basename(f.path),
            "last_indexed_at": f.last_indexed_at,
            "checksum": f.checksum,
        }
        for f in files
    ]


@router.post("/upload")
async def upload_library_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = CurrentUser,
) -> dict[str, Any]:
    """Upload a file to the global knowledge base and trigger indexing."""
    repo = await get_library_repo(db)

    # Save file to LIBRARY_ROOT
    file_path = os.path.join(settings.LIBRARY_ROOT, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to save uploaded file {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Trigger indexing
    indexing_service = IndexingService()
    try:
        await indexing_service.index_file(file_path, repo.id, force=True)
    except Exception as e:
        logger.error(f"Failed to index library file {file.filename}: {e}")
        # We still return success for upload, but maybe with a warning?
        # For now, let's raise error to be safe.
        raise HTTPException(status_code=500, detail=f"Upload succeeded but indexing failed: {str(e)}")

    return {"message": "File uploaded and indexed successfully", "filename": file.filename}


@router.delete("/files/{file_id}")
async def delete_library_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = CurrentUser,
) -> dict[str, Any]:
    """Delete a file from the global knowledge base and clean index."""
    repo = await get_library_repo(db)

    stmt = select(SourceFile).where(SourceFile.id == file_id, SourceFile.repository_id == repo.id)
    result = await db.execute(stmt)
    source_file = result.scalars().first()

    if not source_file:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = os.path.join(settings.LIBRARY_ROOT, source_file.path)

    # Trigger removal from index
    indexing_service = IndexingService()
    try:
        await indexing_service.remove_file(file_path, repo.id)
    except Exception as e:
        logger.error(f"Failed to remove library file {source_file.path} from index: {e}")

    # Remove physical file
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.warning(f"Failed to remove physical file {file_path}: {e}")

    return {"message": "File deleted successfully"}
