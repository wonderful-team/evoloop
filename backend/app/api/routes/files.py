import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.schemas.files import FileNode, FileContent, OpenFileRequest, OpenFileResponse, FileUploadResponse, \
    FileSearchResult, FileNameSearchResult, CreateFileRequest
from app.domain.project.utils import get_project_path
from app.core.file import TreeService, FileSearcher, FileTraverser, read_file, is_ignored_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_id}/files", tags=["files"])


@router.get("", response_model=list[FileNode])
async def list_files(project_id: int, path: str | None = None):
    """
    Get file tree for a project.
    If project_id is 0, returns workspace root files (Global Mode).
    If path is None, returns root.
    """
    if project_id == 0:
        from app.infrastructure.config.service import SystemConfigService
        root_path = SystemConfigService.get_value("WORKSPACE_ROOT")
        if not root_path:
            raise HTTPException(status_code=404, detail="WORKSPACE_ROOT not configured")
    else:
        root_path = await get_project_path(project_id)
        
    if not root_path:
        raise HTTPException(status_code=404, detail="Project path not found")

    # Use unified TreeService for JSON tree generation
    nodes_data = TreeService.get_json_tree(root_path, rel_path=path or "", max_depth=1)
    
    return [FileNode(**node) for node in nodes_data]


@router.get("/content", response_model=FileContent)
async def get_file_content(project_id: int, path: str = Query(..., min_length=1)):
    """
    Read file content.
    """
    root_path = await get_project_path(project_id)
    if not root_path:
        raise HTTPException(status_code=404, detail="Project path not found")

    full_path = os.path.join(root_path, path)
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    # Extension detection
    ext = os.path.splitext(full_path)[1].lower()
    
    try:
        result = read_file(full_path)
        return FileContent(content=result.content, language=ext.lstrip("."))
    except Exception as e:
        logger.error(f"Error reading file {full_path}: {e}")
        raise HTTPException(status_code=500, detail="Error reading file")


@router.get("/raw")
async def get_raw_file(project_id: int, path: str = Query(..., min_length=1)):
    """
    Get raw file content (for previewing images, PDFs, etc).
    """
    root_path = await get_project_path(project_id)
    if not root_path:
        raise HTTPException(status_code=404, detail="Project path not found")

    target_file = os.path.join(root_path, path.lstrip("/"))

    # Security check
    if not os.path.commonpath([root_path, target_file]) == root_path:
        raise HTTPException(403, "Access denied")

    if not os.path.exists(target_file) or not os.path.isfile(target_file):
        raise HTTPException(404, "File not found")

    return FileResponse(target_file)


@router.post("/open")
async def open_file(project_id: int, req: OpenFileRequest):
    """
    Open file in system default application.
    """
    root_path = await get_project_path(project_id)
    if not root_path:
        raise HTTPException(status_code=404, detail="Project path invalid")

    target_file = os.path.join(root_path, req.path.lstrip("/"))

    # Security check
    if not os.path.commonpath([root_path, target_file]) == root_path:
        raise HTTPException(403, "Access denied")

    if not os.path.exists(target_file):
        raise HTTPException(404, "File not found")

    try:
        if sys.platform == "darwin":
            subprocess.run(["open", target_file], check=True)
        elif sys.platform == "win32":
            os.startfile(target_file)
        else:
            subprocess.run(["xdg-open", target_file], check=True)
        return OpenFileResponse(status="success", message="File opened")
    except Exception as e:
        logger.error(f"Failed to open file {target_file}: {e}")
        raise HTTPException(500, f"Failed to open file: {str(e)}")


@router.post("", response_model=FileNode)
async def create_file(project_id: int, req: CreateFileRequest):
    """
    Create or overwrite a file.
    """
    root_path = await get_project_path(project_id)
    if not root_path:
        raise HTTPException(status_code=404, detail="Project path invalid")

    target_file = os.path.join(root_path, req.path.lstrip("/"))

    # Security check
    if not os.path.commonpath([root_path, target_file]) == root_path:
        raise HTTPException(403, "Access denied")

    try:
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        from app.core.file import write_file
        write_file(target_file, req.content)

        return FileNode(name=os.path.basename(target_file), path=req.path, type="file")
    except Exception as e:
        logger.error(f"Failed to write file {target_file}: {e}")
        raise HTTPException(500, f"Failed to write file: {str(e)}")


@router.post("/upload")
async def upload_file(project_id: int, file: UploadFile = File(...)):
    """
    Upload a file to project's 'uploads' directory.
    """
    root_path = await get_project_path(project_id)
    if not root_path:
        raise HTTPException(status_code=404, detail="Project path invalid")

    upload_dir = os.path.join(root_path, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    filename = os.path.basename(file.filename or "uploaded_file")
    target_path = os.path.join(upload_dir, filename)

    if os.path.exists(target_path):
        base, ext = os.path.splitext(filename)
        filename = f"{base}_{int(time.time())}{ext}"
        target_path = os.path.join(upload_dir, filename)

    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        rel_path = f"uploads/{filename}"
        url = f"/api/projects/{project_id}/files/raw?path={rel_path}"
        return FileUploadResponse(url=url, filename=filename, path=rel_path)

    except Exception as e:
        logger.error(f"Failed to upload file {target_path}: {e}")
        raise HTTPException(500, f"Failed to upload file: {str(e)}")


@router.get("/search", response_model=list[FileSearchResult])
async def search_files(project_id: int, q: str):
    """
    Search for text content within project files (standardized search).
    """
    if not q or len(q.strip()) < 2:
        return []

    root_path = await get_project_path(project_id)
    if not root_path:
        return []

    # Use unified FileSearcher
    results_data = await FileSearcher.search_content(q, root_path, limit=50)
    
    return [
        FileSearchResult(
            file=os.path.relpath(r["file"], root_path),
            line=r["line"],
            content=r["content"]
        ) for r in results_data
    ]


@router.get("/search_name", response_model=list[FileNameSearchResult])
async def search_files_by_name(project_id: int, q: str):
    """
    Search for files by name (standardized traversal).
    """
    if not q or len(q.strip()) < 1:
        return []

    root_path = await get_project_path(project_id)
    if not root_path:
        return []

    # Use unified FileTraverser
    q_lower = q.lower()
    results = []
    count = 0
    
    for full_path in FileTraverser.walk(root_path):
        file_name = os.path.basename(full_path)
        if q_lower in file_name.lower():
            rel_path = os.path.relpath(full_path, root_path)
            results.append(FileNameSearchResult(name=file_name, path=rel_path, type="file"))
            count += 1
            if count >= 20:
                break

    return results
