import os
import logging
from typing import List, Dict, Optional, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
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
    IGNORE_DIRS = {'.git', 'node_modules', '__pycache__', 'dist', 'build', '.idea', '.vscode', '.DS_Store'}
    
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
    except UnicodeDecodeError:
        return FileContent(content="// Binary file or unsupported encoding", language="unknown")
    except Exception as e:
        logger.error(f"Error reading file {target_file}: {e}")
        raise HTTPException(500, "Error reading file")
