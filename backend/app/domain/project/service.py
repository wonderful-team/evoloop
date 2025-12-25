import os
import logging
import json
from typing import Dict, Optional, List
from threading import Lock
from app.core.config import settings
from app.domain.system.service import SystemConfigService
from app.infrastructure.external.imagicbox import imagicbox_client

logger = logging.getLogger(__name__)

class ProjectContextManager:
    """
    Manages the working directory context for different threads (sessions).
    This allows the server to support multiple active projects simultaneously.
    Integrates with ImagicBox API for project discovery.
    """
    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ProjectContextManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        # Mapping: thread_id -> working_directory path
        self._thread_contexts: Dict[str, str] = {}
        # Default fallback directory (from Settings/DB)
        db_root = SystemConfigService.get_value("PROJECTS_ROOT")
        self._default_root = os.path.abspath(db_root if db_root else settings.PROJECTS_ROOT)
        logger.info(f"ProjectContextManager initialized. Default root: {self._default_root}")

    def set_working_directory(self, thread_id: str, path: str):
        """Set the working directory for a specific thread."""
        if not path:
             logger.warning(f"Attempted to set empty path for thread {thread_id}")
             return

        # With API-driven projects, the path might be on a remote server (conceptually)
        # But for EvoLoop to work, it must be mounted/present locally at 'path'.
        # We assume 'external_path' from API maps to a valid local path.
        if not os.path.exists(path):
            logger.warning(f"Setting working directory to non-existent path: {path}. Agent actions might fail.")

        self._thread_contexts[thread_id] = path
        logger.info(f"Updated working directory for thread {thread_id} -> {path}")

    def get_working_directory(self, thread_id: str) -> str:
        """Get the working directory for a specific thread. Returns default if not set."""
        path = self._thread_contexts.get(thread_id)
        if path:
            return path
        return self._default_root
    
    def clear_context(self, thread_id: str):
        """Remove context for a thread."""
        if thread_id in self._thread_contexts:
            del self._thread_contexts[thread_id]
            logger.info(f"Cleared context for thread {thread_id}")

    async def scan_projects(self) -> List[Dict]:
        """
        Fetch projects from ImagicBox API.
        Replaces legacy filesystem scanning.
        """
        try:
            # 1. Fetch from API
            resp = imagicbox_client.get_projects(page=1, page_size=100)
            
            if resp.get("code") != 0:
                logger.error(f"Failed to fetch projects from API: {resp.get('message')}")
                return []
                
            data = resp.get("data", {})
            api_projects = data.get("list", [])
            
            projects = []
            for p in api_projects:
                # Map API fields to Internal Schema
                name = p.get("project_name", "Unknown")
                desc = p.get("project_desc", "")
                
                # 'external_path' is what we rely on for local file access
                # The API returns the path where the project *should* be.
                path = p.get("external_path", "")
                
                # Validation: Does it exist locally?
                # If not, mark it. We might want to show it as "Not Found" in UI 
                # or just hide it. Current decision: Show it but flag it.
                exists = os.path.exists(path) if path else False
                
                projects.append({
                    "id": p.get("project_id"), # Integer ID from Member Center
                    "name": name,
                    "description": desc,
                    "path": path,
                    "exists_locally": exists,
                    "status_text": p.get("status_text", ""),
                    "owner": p.get("owner_member_name", "")
                })
                
            return projects
            

        except Exception as e:
            logger.error(f"scan_projects failed: {e}")
            return []

    async def get_project_by_id(self, project_id: int) -> Optional[Dict]:
        """Get project details by numeric ID."""
        projects = await self.scan_projects()
        for p in projects:
            if p.get("id") == project_id:
                return p
        return None

# Global instance
project_context_manager = ProjectContextManager()
