import os
import asyncio
import logging
from typing import List, Dict, Optional, Any
from fastapi import APIRouter, HTTPException, Query
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
import shutil
import subprocess
import sys
from app.domain.project.service import project_context_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_id}/files", tags=["files"])

class FileNode(BaseModel):
    name: str # display name
    path: str # relative path to project root
    type: str # 'file' or 'directory'
    children: Optional[List['FileNode']] = None

@router.get("", response_model=List[FileNode])
async def list_files(project_id: int, path: Optional[str] = None):
    """
    Get file tree for a project. 
    If path is None, returns root.
    Use path to traverse deeper (though UI might just want full tree?).
    Let's implement a recursive full tree for now (depth limited) or single level.
    Given "IDE-like" request, single level with lazy load is safer for huge repos, 
    but full tree is nicer for UX. 
    Let's do full tree with .gitignore respect and max depth.
    """
    project = await project_context_manager.get_project_by_id(project_id)
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")
         
    root_path = project.get("path")
    if not root_path or not os.path.exists(root_path):
        raise HTTPException(status_code=404, detail=f"Project path not found locally: {root_path}")
    
    # Simple recursive walker ignoring heavy dirs
    from app.constants import BLACKLIST_DIRS
    # Combine with local ignores if needed, or just use global
    IGNORE_DIRS = set(BLACKLIST_DIRS).union({'.idea', '.vscode', '.DS_Store', 'dist', 'build'})
    
    def build_tree(current_path: str, rel_path: str = "") -> List[FileNode]:
        nodes = []
        try:
            with os.scandir(current_path) as it:
                entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
                for entry in entries:
                    if entry.name in IGNORE_DIRS:
                        continue
                    if entry.name.startswith('.'): # Skip hidden files heavily? Maybe make optional.
                        pass
                        
                    node_rel_path = os.path.join(rel_path, entry.name)
                    
                    node = FileNode(
                        name=entry.name,
                        path=node_rel_path,
                        type="directory" if entry.is_dir() else "file"
                    )
                    
                    if entry.is_dir():
                        # Determine recursion. For now, let's just go deep? 
                        # Or maybe just shallow? 
                        # Since user asked for "File Tree", frontend might want lazy loading.
                        # But simpler start is just 2-3 levels or flat list.
                        # Let's do lazy loading if 'path' param is supported?
                        # Actually, let's try to return full structure or limit depth.
                        # For simple usage, full tree is dangerous if huge.
                        # COMPROMISE: If 'path' arg is provided, return children of that path. 
                        # If 'path' is empty/root, return root items.
                        # BUT the user also wants "Recursive file tree".
                        # Let's implement full recursion but cap depth or file count if needed.
                        pass 
                    
                    nodes.append(node)
        except PermissionError:
            pass
        return nodes

    # Revised approach: 
    # If client asks for root, we give root.
    # Client will recursively call us for subdirs (Lazy Loading).
    # This is safer.
    
    target_dir = os.path.join(root_path, path) if path else root_path
    
    # Defense against traversal
    if not os.path.commonpath([root_path, target_dir]) == root_path:
        raise HTTPException(403, "Access denied")
        
    return build_tree(target_dir, path or "")

class FileContent(BaseModel):
    content: str
    language: str

@router.get("/content", response_model=FileContent)
async def get_file_content(project_id: int, path: str = Query(..., min_length=1)):
    """
    Read file content.
    """
    project = await project_context_manager.get_project_by_id(project_id)
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")
         
    root_path = project.get("path")
    if not root_path or not os.path.exists(root_path):
        raise HTTPException(status_code=404, detail=f"Project path not found locally: {root_path}")
        
    target_file = os.path.join(root_path, path.lstrip('/'))
    
    if not os.path.commonpath([root_path, target_file]) == root_path:
        raise HTTPException(403, "Access denied")
        
    if not os.path.exists(target_file) or not os.path.isfile(target_file):
        raise HTTPException(404, "File not found")
        
    # Simple extension detection
    ext = os.path.splitext(target_file)[1].lower()
    
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            content = f.read()
            return FileContent(content=content, language=ext.lstrip('.'))
    except Exception as e:
        logger.error(f"Error reading file {target_file}: {e}")
        raise HTTPException(500, "Error reading file")

@router.get("/raw")
async def get_raw_file(project_id: int, path: str = Query(..., min_length=1)):
    """
    Get raw file content (for previewing images, PDFs, etc).
    """
    project = await project_context_manager.get_project_by_id(project_id)
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")
         
    root_path = project.get("path")
    if not root_path or not os.path.exists(root_path):
        raise HTTPException(status_code=404, detail=f"Project path not found locally: {root_path}")
        
    target_file = os.path.join(root_path, path.lstrip('/'))
    
    if not os.path.commonpath([root_path, target_file]) == root_path:
        raise HTTPException(403, "Access denied")
        
    if not os.path.exists(target_file) or not os.path.isfile(target_file):
        raise HTTPException(404, "File not found")

    return FileResponse(target_file)

class OpenFileRequest(BaseModel):
    path: str

@router.post("/open")
async def open_file(project_id: int, req: OpenFileRequest):
    """
    Open file in system default application.
    """
    project = await project_context_manager.get_project_by_id(project_id)
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")
         
    root_path = project.get("path")
    if not root_path or not os.path.exists(root_path):
        raise HTTPException(status_code=404, detail="Project path invalid")
    
    target_file = os.path.join(root_path, req.path.lstrip('/'))
    
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
        return {"status": "success", "message": "File opened"}
    except Exception as e:
        logger.error(f"Failed to open file {target_file}: {e}")
        raise HTTPException(500, f"Failed to open file: {str(e)}")

class CreateFileRequest(BaseModel):
    path: str
    content: str

@router.post("", response_model=FileNode)
async def create_file(project_id: int, req: CreateFileRequest):
    """
    Create or overwrite a file.
    """
    project = await project_context_manager.get_project_by_id(project_id)
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")
         
    root_path = project.get("path")
    if not root_path or not os.path.exists(root_path):
        raise HTTPException(status_code=404, detail="Project path invalid")
    
    target_file = os.path.join(root_path, req.path.lstrip('/'))
    
    # Security check
    if not os.path.commonpath([root_path, target_file]) == root_path:
        raise HTTPException(403, "Access denied")
        
    try:
        os.makedirs(os.path.dirname(target_file), exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(req.content)
            
        return FileNode(
            name=os.path.basename(target_file),
            path=req.path,
            type="file"
        )
    except Exception as e:
        logger.error(f"Failed to write file {target_file}: {e}")
        raise HTTPException(500, f"Failed to write file: {str(e)}")

@router.post("/upload")
async def upload_file(project_id: int, file: UploadFile = File(...)):
    """
    Upload a file to project's 'uploads' directory.
    Returns the URL to access it via /raw endpoint.
    """
    project = await project_context_manager.get_project_by_id(project_id)
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")
         
    root_path = project.get("path")
    if not root_path or not os.path.exists(root_path):
        raise HTTPException(status_code=404, detail="Project path invalid")
    
    upload_dir = os.path.join(root_path, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    # Generate unique name if needed, or secure filename
    # For chat attachments, usually want to keep original name if possible or uuid
    # Let's use original name but prepend timestamp/uuid if conflict?
    # For now, simple override or unique.
    filename = os.path.basename(file.filename or "uploaded_file")
    target_path = os.path.join(upload_dir, filename)
    
    # Simple dedupe
    if os.path.exists(target_path):
        base, ext = os.path.splitext(filename)
        import time
        filename = f"{base}_{int(time.time())}{ext}"
        target_path = os.path.join(upload_dir, filename)

    try:
        with open(target_path, "wb") as buffer:
             shutil.copyfileobj(file.file, buffer)
             
        # Return URL. 
        # API URL structure: /api/projects/{id}/files/raw?path=uploads/{filename}
        # We return absolute path or relative? 
        # ChatInput expects a URL it can put in [File: URL]. 
        # The URL should be accessible by the Agent (who reads file?) or by the User (who clicks link?).
        # If Agent reads it, it might need local path. 
        # If User clicks, they need http url.
        # Let's return the API URL.
        # Assuming format: /api/projects/{project_id}/files/raw?path=uploads/{filename}
        # We don't know the full domain here easily without request context, but we can return relative API path.
        # Frontend usually prepends base or handles it?
        # Actually `sdk.gen.ts` uses relative paths.
        # So we return `/api/projects/{project_id}/files/raw?path=uploads/{filename}`
        
        rel_path = f"uploads/{filename}"
        url = f"/api/projects/{project_id}/files/raw?path={rel_path}"
        return {"url": url, "filename": filename, "path": rel_path}
        
    except Exception as e:
        logger.error(f"Failed to upload file {target_path}: {e}")
        raise HTTPException(500, f"Failed to upload file: {str(e)}")

@router.get("/search", response_model=List[dict])
async def search_files(project_id: int, q: str):
    """
    Search for text content within project files (simple grep).
    """
    if not q or len(q.strip()) < 2:
        return []
        
    project = await project_context_manager.get_project_by_id(project_id)
    if not project:
         raise HTTPException(status_code=404, detail="Project not found")
    
    root_path = project.get("path")
    if not root_path or not os.path.exists(root_path):
        return []

    results = []
    try:
        # Use grep to find matches
        # -r: recursive
        # -i: case insensitive
        # -n: show line number
        # -I: ignore binary files
        # --exclude-dir: ignore common junk
        from app.utils.process import run_async_command
        
        cmd = [
            "grep", "-r", "-i", "-n", "-I", 
            "--exclude-dir={.git,.venv,node_modules,__pycache__,dist,build,.evoloop}", 
            q, 
            root_path
        ]
        
        # run_async_command
        result = await run_async_command(cmd)
        stdout, stderr = result.stdout, result.stderr
        
        if stdout:
            lines = stdout.splitlines()
            for line in lines[:50]: # Limit to 50 hits
                try:
                    # Grep output format: filename:line:content
                    # But filepath is absolute or relative depending on grep. 
                    # Usually grep -r path outputs path/filename:line:content
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        file_path_part = parts[0]
                        line_num = parts[1]
                        content = parts[2]
                        
                        # Fix path if it is absolute
                        if os.path.isabs(file_path_part):
                            rel_path = os.path.relpath(file_path_part, root_path)
                        else:
                             # If grep was run on directory, it outputs dir/file
                             # We passed root_path as argument.
                             # If root_path is absolute, output is absolute.
                             rel_path = os.path.relpath(file_path_part, root_path)

                        results.append({
                            "file": rel_path,
                            "line": int(line_num),
                            "content": content.strip()[:200]
                        })
                except Exception:
                    continue
                    
    except Exception as e:
        logger.error(f"Search failed: {e}")
        
    return results
