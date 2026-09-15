import logging
import os
import shutil
import subprocess
import sys
import time

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import CurrentUserOptional
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
from app.core.file.traverser import TraverseOptions
from app.core.project.utils import get_project_path, get_workspace_root
from app.core.security.path import get_allowed_roots, is_under_allowed_root

logger = logging.getLogger(__name__)
router = APIRouter(tags=["files"])


def _assert_path_allowed(target_path: str) -> None:
    """Check path against the same security boundary as Agent tools.

    Allowed roots (see ``app/core/security/path.py``): the current project /
    working directory, ``WORKSPACE_ROOT``, the app data dir (``~/.evoloop``)
    and ``ALLOWED_PATH_PREFIXES``. This mirrors what Agent tools may touch, so
    ``file://`` previews and downloads of project files work while arbitrary
    paths stay blocked.
    """
    normalized = os.path.realpath(os.path.expanduser(target_path))

    # Allow chat upload directory
    upload_dir = os.path.realpath(settings.CHAT_UPLOAD_DIR)
    if normalized.startswith(upload_dir):
        return

    # Allow all Agent-tool roots (WORKSPACE_ROOT, ~/.evoloop, allowed prefixes,
    # and the resolved project/working dirs when available).
    if is_under_allowed_root(normalized, allowed_roots=get_allowed_roots()):
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
        root_path = get_workspace_root()
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
        logger.exception(f"Error reading file {full_path}: {e}")
        raise HTTPException(status_code=500, detail="Error reading file")


async def _resolve_upload_file(normalized: str, member_id: int = 0) -> str | None:
    """Resolve uploads/{rel} to a physical file（多租户按归属收权）。

    - ``uploads/{thread_id}/file``：thread 必须归属该 member（查 Conversation.member_id）
    - member 物理根（``<member workspace>/uploads``）下的文件：直接可用
    - global/tmp/平铺 legacy 文件：多租户下一律拒绝越查其他用户目录（fail-closed）
    - 单用户模式保持原目录搜索行为
    """
    from app.core.config import settings as _settings
    from app.models import Conversation

    rel_path = normalized[len("uploads/") :].lstrip("/")
    filename = os.path.basename(rel_path)  # 归一化，拒绝 ../ 穿越

    # 1) 线程隔离目录（uploads/{thread_id}/…）——归属校验
    parts = rel_path.split("/", 1)
    first = parts[0]
    thread_like = first not in ("global",) and not first.startswith("tmp_")
    if thread_like and ("/" in rel_path):
        thread_path = os.path.join(settings.CHAT_UPLOAD_DIR, first, filename)
        if os.path.isfile(thread_path):
            if _settings.MULTI_TENANT_MODE:
                async with session_scope() as session:
                    conv = await session.get(Conversation, first)
                    if not conv or int(conv.member_id or 0) != int(member_id or 0):
                        return None
            return thread_path

    # 2) member 物理根 uploads（多租户新落位）
    if _settings.MULTI_TENANT_MODE:
        from app.core.project.utils import (
            current_member_id,
            resolve_member_workspace_root,
        )

        mid = int(member_id or 0) or current_member_id()
        member_root = resolve_member_workspace_root(mid) if mid else ""
        if not member_root:
            return None
        member_uploads = os.path.join(member_root, "uploads")
        if os.path.isfile(os.path.join(member_uploads, filename)):
            return os.path.join(member_uploads, filename)
        for _root, _dirs, files in os.walk(member_uploads):
            if filename in files:
                return os.path.join(_root, filename)
        return None

    # 3) 单用户 legacy 行为：线程目录 + 全目录搜索
    target_file = os.path.join(settings.CHAT_UPLOAD_DIR, rel_path)
    if not os.path.exists(target_file):
        for root, _dirs, files in os.walk(settings.CHAT_UPLOAD_DIR):
            if rel_path in files:
                target_file = os.path.join(root, rel_path)
                break
    return target_file if target_file and os.path.isfile(target_file) else None


@router.get("/raw")
async def get_raw_file(
    path: str = Query(..., min_length=1),
    project_id: int | None = Query(None),
    _current_user: CurrentUserOptional = None,
):
    """
    Get raw file content (for previewing images, PDFs, etc).

    两种模式：
    1. 带 project_id：项目内文件（相对路径）
    2. 不带 project_id：uploads/ 附件或外部绝对路径（受 ALLOWED_PATH_PREFIXES 限制）

    多租户 fail-closed：必须携带有效 member 身份；uploads 仅解析归属自己
    thread/member 物理根的文件；裸绝对路径模式（宿主白名单）对成员关闭。
    """
    from app.core.config import settings as _settings

    normalized = path.lstrip("/")

    if _settings.MULTI_TENANT_MODE and not _current_user:
        raise HTTPException(401, "member authentication required")

    # 聊天附件统一路由：uploads/ 路径都指向自己（或归属）目录
    if normalized.startswith("uploads/"):
        target_file = await _resolve_upload_file(
            normalized, _current_user.id if _current_user else 0
        )
        if target_file:
            return FileResponse(target_file)
        raise HTTPException(404, "File not found")

    # 带 project_id：项目内文件
    if project_id is not None:
        root_path = await get_project_path(
            project_id, _current_user.id if _current_user else 0
        )
        if not root_path:
            raise HTTPException(status_code=404, detail="Project path not found")

        target_file = os.path.join(root_path, normalized)

        # Security check
        if not os.path.commonpath([root_path, target_file]) == root_path:
            raise HTTPException(403, "Access denied")

        if not os.path.exists(target_file) or not os.path.isfile(target_file):
            raise HTTPException(404, "File not found")
        return FileResponse(target_file)

    # 不带 project_id：外部绝对路径 —— 多租户下对成员关闭宿主白名单模式
    from app.core.config import settings as _settings

    if _settings.MULTI_TENANT_MODE:
        raise HTTPException(403, "absolute path access disabled in multi-tenant mode")

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
        logger.exception(f"Failed to open file {target_file}: {e}")
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
        logger.exception(f"Failed to write file {target_file}: {e}")
        raise HTTPException(500, f"Failed to write file: {str(e)}")


@router.post("/upload")
async def upload_file(
    project_id: int = Query(...),
    file: UploadFile = File(...),
    thread_id: str | None = Form(None),
    session_id: str | None = Form(None),
    _current_user: CurrentUserOptional = None,
):
    """
    聊天输入框附件上传。

    隔离策略：
    1. 多租户：物理落位 ``<member workspace>/uploads/``（member 级私有根），
       thread 会话目录为 ``uploads/{thread_id}/``；无身份一律 401。
       thread 归属他人时拒绝写入。
    2. 单用户：沿用 uploads/{thread_id|tmp_$session|global}/（向后兼容）。
    """
    from app.core.config import settings as _settings

    member_id = _current_user.id if _current_user else 0
    if _settings.MULTI_TENANT_MODE:
        if not _current_user:
            raise HTTPException(401, "member authentication required")

    # 确定物理子目录
    if _settings.MULTI_TENANT_MODE:
        from app.core.project.utils import resolve_member_workspace_root

        member_root = resolve_member_workspace_root(member_id)
        if not member_root:
            raise HTTPException(403, "member workspace unavailable")
        base_upload_root = os.path.join(member_root, "uploads")
        sub_dir = "global"
        if thread_id:
            from app.infrastructure.database import session_scope as _scope
            from app.models import Conversation as _Conversation

            async with _scope() as session:
                conv = await session.get(_Conversation, thread_id)
                if not conv or int(conv.member_id or 0) != member_id:
                    raise HTTPException(403, "thread does not belong to current member")
            sub_dir = thread_id
        elif session_id:
            sub_dir = f"tmp_{session_id}"
        upload_dir = os.path.join(base_upload_root, sub_dir)
    else:
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
        logger.exception(f"Failed to upload file {target_path}: {e}")
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
        logger.exception(f"Failed to upload to workspace {target_file}: {e}")
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
            content=r["content"],
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
    matches = []

    options = TraverseOptions(include_dirs=True)
    for full_path in FileTraverser.walk(root_path, options=options):
        file_name = os.path.basename(full_path)
        if q_lower in file_name.lower():
            rel_path = os.path.relpath(full_path, root_path)
            is_dir = os.path.isdir(full_path)
            depth = rel_path.count(os.sep)
            fns_result = FileNameSearchResult(
                name=file_name,
                path=rel_path,
                type="directory" if is_dir else "file",
            )
            matches.append((depth, fns_result))
            # Collect a reasonable sample size before sorting
            if len(matches) >= 300:
                break

    # Sort by depth (shallow to deep), then by name length
    matches.sort(key=lambda x: (x[0], len(x[1].name)))

    return [m[1] for m in matches[:20]]


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
        logger.exception(f"Failed to create directory {target_dir}: {e}")
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
    if (
        not os.path.commonpath([root_path, source_file]) == root_path
        or not os.path.commonpath([root_path, target_file]) == root_path
    ):
        raise HTTPException(403, "Access denied")

    if not os.path.exists(source_file):
        raise HTTPException(404, "Source not found")

    if os.path.exists(target_file):
        raise HTTPException(409, "Target already exists")

    try:
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        shutil.move(source_file, target_file)

        is_dir = os.path.isdir(target_file)
        return FileNode(
            name=os.path.basename(target_file),
            path=req.target_path,
            type="directory" if is_dir else "file",
        )
    except Exception as e:
        logger.exception(f"Failed to move {source_file} to {target_file}: {e}")
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
        return BaseAPIResponse(success=True, message="File already deleted")

    try:
        if os.path.isdir(target_file):
            shutil.rmtree(target_file)
        else:
            os.remove(target_file)
        return BaseAPIResponse(success=True, message="File deleted")
    except Exception as e:
        logger.exception(f"Failed to delete {target_file}: {e}")
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
        logger.exception(f"Error reading file {target_path}: {e}")
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
