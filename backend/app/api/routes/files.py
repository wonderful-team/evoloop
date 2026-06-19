import logging
import os
import shutil
import subprocess
import sys
import time

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.schemas.files import (
    CreateFileRequest,
    DownloadFileRequest,
    FileContent,
    FileNameSearchResult,
    FileNode,
    FileSearchResult,
    FileUploadResponse,
    MkdirRequest,
    MoveFileRequest,
    OpenFileRequest,
    OpenFileResponse,
    ReadFileRequest,
    ReadFileResponse,
)
from app.api.schemas.responses import BaseAPIResponse
from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.file import (
    FileSearcher,
    FileTraverser,
    TreeService,
    read_file,
    resolve_path,
)
from app.core.project.utils import get_project_path

logger = logging.getLogger(__name__)
router = APIRouter(tags=["files"])


def _assert_path_allowed(target_path: str) -> None:
    """Check path against the same security boundary as Agent tools."""
    normalized = os.path.realpath(os.path.expanduser(target_path))

    # Allow chat upload directory
    upload_dir = os.path.realpath(settings.CHAT_UPLOAD_DIR)
    if normalized.startswith(upload_dir):
        return

    # Allow all ALLOWED_PATH_PREFIXES (same as resolve_and_validate_path)
    for prefix in settings.ALLOWED_PATH_PREFIXES:
        expanded = os.path.realpath(os.path.expanduser(prefix))
        if normalized.startswith(expanded):
            return

    raise HTTPException(403, "Access denied: path not in allowed prefixes")


@router.get("/", response_model=list[FileNode])
async def list_files(
    project_id: int = Query(...),
    path: str | None = None,
):
    """
    Get file tree for a project.
    If project_id is DEFAULT_PROJECT_ID (0, global mode), returns workspace root files.
    If path is None, returns root.
    """
    if project_id == DEFAULT_PROJECT_ID:
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
async def get_file_content(
    project_id: int = Query(...),
    path: str = Query(..., min_length=1),
):
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


def _resolve_upload_file(normalized: str) -> str | None:
    """Resolve uploads/{filename} to a physical file in CHAT_UPLOAD_DIR."""
    rel_path = normalized[len("uploads/"):]
    target_file = os.path.join(settings.CHAT_UPLOAD_DIR, rel_path)

    # 如果根目录下没有，尝试在子目录中找（适配隔离后的路径）
    if not os.path.exists(target_file):
        for root, _dirs, files in os.walk(settings.CHAT_UPLOAD_DIR):
            if rel_path in files:
                target_file = os.path.join(root, rel_path)
                break

    if target_file and os.path.exists(target_file) and os.path.isfile(target_file):
        return target_file
    return None


@router.get("/raw")
async def get_raw_file(
    path: str = Query(..., min_length=1),
    project_id: int | None = Query(None),
):
    """
    Get raw file content (for previewing images, PDFs, etc).

    两种模式：
    1. 带 project_id：项目内文件（相对路径）
    2. 不带 project_id：外部绝对路径或 uploads/ 路径，受 ALLOWED_PATH_PREFIXES 限制
    """
    normalized = path.lstrip("/")

    # 聊天附件统一路由：uploads/ 路径都指向 CHAT_UPLOAD_DIR
    if normalized.startswith("uploads/"):
        target_file = _resolve_upload_file(normalized)
        if target_file:
            return FileResponse(target_file)
        raise HTTPException(404, "File not found")

    # 带 project_id：项目内文件
    if project_id is not None:
        root_path = await get_project_path(project_id)
        if not root_path:
            raise HTTPException(status_code=404, detail="Project path not found")

        target_file = os.path.join(root_path, normalized)

        # Security check
        if not os.path.commonpath([root_path, target_file]) == root_path:
            raise HTTPException(403, "Access denied")

        if not os.path.exists(target_file) or not os.path.isfile(target_file):
            raise HTTPException(404, "File not found")
        return FileResponse(target_file)

    # 不带 project_id：外部绝对路径
    expanded = os.path.expanduser(path)
    target_file = resolve_path(expanded, base_path=None)
    if not target_file:
        raise HTTPException(400, f"Invalid path: {path}")

    _assert_path_allowed(target_file)

    if not os.path.exists(target_file) or not os.path.isfile(target_file):
        raise HTTPException(404, "File not found")
    return FileResponse(target_file)


@router.post("/open")
async def open_file(
    req: OpenFileRequest,
    project_id: int = Query(...),
):
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


@router.post("/", response_model=FileNode)
async def create_file(
    req: CreateFileRequest,
    project_id: int = Query(...),
):
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
async def upload_file(
    project_id: int = Query(...),
    file: UploadFile = File(...),
    thread_id: str | None = Form(None),
    session_id: str | None = Form(None),
):
    """
    聊天输入框附件上传。

    隔离策略：
    1. 如果指定了 thread_id: 存入 uploads/{thread_id}/
    2. 如果指定了 session_id: 存入 uploads/tmp_{session_id}/ (待转正)
    3. 否则: 存入 uploads/global/ (兜底)
    """
    # 确定物理子目录
    sub_dir = "global"
    if thread_id:
        sub_dir = thread_id
    elif session_id:
        sub_dir = f"tmp_{session_id}"

    upload_dir = os.path.join(settings.CHAT_UPLOAD_DIR, sub_dir)
    os.makedirs(upload_dir, exist_ok=True)

    filename = os.path.basename(file.filename or "uploaded_file")
    target_path = os.path.join(upload_dir, filename)

    # 处理同名冲突（在同一个会话/session内）
    if os.path.exists(target_path):
        base, ext = os.path.splitext(filename)
        filename = f"{base}_{int(time.time())}{ext}"
        target_path = os.path.join(upload_dir, filename)

    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 逻辑路径依然返回 uploads/{filename}，前端不需要感知物理子目录
        rel_path = f"uploads/{filename}"
        url = f"/api/v1/files/raw?project_id={project_id}&path={rel_path}"

        return FileUploadResponse(url=url, filename=filename, path=rel_path)

    except Exception as e:
        logger.error(f"Failed to upload file {target_path}: {e}")
        raise HTTPException(500, f"Failed to upload file: {str(e)}")


@router.post("/workspace_upload", response_model=FileNode)
async def workspace_upload(
    project_id: int = Query(...),
    file: UploadFile = File(...),
    target_dir: str = Form(""),
    overwrite: bool = Form(False),
):
    """
    Upload a binary file directly into the project workspace.
    """
    root_path = await get_project_path(project_id)
    if not root_path:
        raise HTTPException(status_code=404, detail="Project path invalid")

    # Clean target_dir to prevent directory traversal
    target_dir = target_dir.lstrip("/")
    target_dir_path = os.path.join(root_path, target_dir)

    filename = os.path.basename(file.filename or "uploaded_file")
    target_file = os.path.join(target_dir_path, filename)

    # Security check: ensure target_file is inside root_path
    if not os.path.commonpath([root_path, target_file]) == root_path:
        raise HTTPException(403, "Access denied")

    if os.path.exists(target_file) and not overwrite:
        raise HTTPException(409, "File already exists")

    try:
        os.makedirs(target_dir_path, exist_ok=True)
        with open(target_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Return relative path for frontend FileNode
        rel_path = os.path.relpath(target_file, root_path)
        return FileNode(name=filename, path=rel_path, type="file")
    except Exception as e:
        logger.error(f"Failed to upload to workspace {target_file}: {e}")
        raise HTTPException(500, f"Failed to upload to workspace: {str(e)}")


@router.get("/search", response_model=list[FileSearchResult])
async def search_files(
    q: str,
    project_id: int = Query(...),
):
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
async def search_files_by_name(
    q: str,
    project_id: int = Query(...),
):
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


@router.post("/mkdir", response_model=FileNode)
async def create_directory(
    req: MkdirRequest,
    project_id: int = Query(...),
):
    """
    Create an empty directory.
    """
    root_path = await get_project_path(project_id)
    if not root_path:
        raise HTTPException(status_code=404, detail="Project path invalid")

    target_dir = os.path.join(root_path, req.path.lstrip("/"))

    # Security check
    if not os.path.commonpath([root_path, target_dir]) == root_path:
        raise HTTPException(403, "Access denied")

    try:
        os.makedirs(target_dir, exist_ok=True)
        return FileNode(name=os.path.basename(target_dir), path=req.path, type="directory")
    except Exception as e:
        logger.error(f"Failed to create directory {target_dir}: {e}")
        raise HTTPException(500, f"Failed to create directory: {str(e)}")


@router.post("/move", response_model=FileNode)
async def move_file(
    req: MoveFileRequest,
    project_id: int = Query(...),
):
    """
    Move or rename a file or directory.
    """
    root_path = await get_project_path(project_id)
    if not root_path:
        raise HTTPException(status_code=404, detail="Project path invalid")

    source_file = os.path.join(root_path, req.source_path.lstrip("/"))
    target_file = os.path.join(root_path, req.target_path.lstrip("/"))

    # Security check
    if not os.path.commonpath([root_path, source_file]) == root_path or \
       not os.path.commonpath([root_path, target_file]) == root_path:
        raise HTTPException(403, "Access denied")

    if not os.path.exists(source_file):
        raise HTTPException(404, "Source not found")

    if os.path.exists(target_file):
        raise HTTPException(409, "Target already exists")

    try:
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        shutil.move(source_file, target_file)

        is_dir = os.path.isdir(target_file)
        return FileNode(name=os.path.basename(target_file), path=req.target_path, type="directory" if is_dir else "file")
    except Exception as e:
        logger.error(f"Failed to move {source_file} to {target_file}: {e}")
        raise HTTPException(500, f"Failed to move: {str(e)}")


@router.delete("/", response_model=BaseAPIResponse)
async def delete_file(
    project_id: int = Query(...),
    path: str = Query(..., min_length=1),
):
    """
    Delete a file or directory.
    """
    root_path = await get_project_path(project_id)
    if not root_path:
        raise HTTPException(status_code=404, detail="Project path invalid")

    target_file = os.path.join(root_path, path.lstrip("/"))

    # Security check
    if not os.path.commonpath([root_path, target_file]) == root_path:
        raise HTTPException(403, "Access denied")

    if not os.path.exists(target_file):
        return BaseAPIResponse(status="success", message="File already deleted")

    try:
        if os.path.isdir(target_file):
            shutil.rmtree(target_file)
        else:
            os.remove(target_file)
        return BaseAPIResponse(status="success", message="File deleted")
    except Exception as e:
        logger.error(f"Failed to delete {target_file}: {e}")
        raise HTTPException(500, f"Failed to delete: {str(e)}")


@router.post("/read", response_model=ReadFileResponse)
async def read_any_file(req: ReadFileRequest):
    """读取任意本地文件内容。

    安全边界复用 Agent 工具的路径权限（ALLOWED_PATH_PREFIXES + uploads）。
    不绑定 project_id，支持 file:// 链接点击预览。
    """
    # Resolve path (supports ~, absolute, relative)
    expanded = os.path.expanduser(req.path)
    target_path = resolve_path(expanded, base_path=None)
    if not target_path:
        raise HTTPException(400, f"Invalid path: {req.path}")

    _assert_path_allowed(target_path)

    if not os.path.exists(target_path):
        raise HTTPException(404, f"File not found: {req.path}")
    if not os.path.isfile(target_path):
        raise HTTPException(400, f"Not a file: {req.path}")

    try:
        result = read_file(target_path)
        return ReadFileResponse(content=result.content)
    except Exception as e:
        logger.error(f"Error reading file {target_path}: {e}")
        raise HTTPException(500, "Error reading file")


@router.post("/download")
async def download_any_file(req: DownloadFileRequest):
    """下载任意本地文件。

    返回 FileResponse，文件名从 path 取 basename。
    安全边界与 read_any_file 相同。
    """
    expanded = os.path.expanduser(req.path)
    target_path = resolve_path(expanded, base_path=None)
    if not target_path:
        raise HTTPException(400, f"Invalid path: {req.path}")

    _assert_path_allowed(target_path)

    if not os.path.exists(target_path) or not os.path.isfile(target_path):
        raise HTTPException(404, "File not found")

    filename = os.path.basename(target_path)
    return FileResponse(
        target_path,
        filename=filename,
        media_type="application/octet-stream",
    )
