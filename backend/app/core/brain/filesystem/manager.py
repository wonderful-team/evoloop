"""
Sandboxed File System Manager.
"""
import logging
import shutil
from pathlib import Path
from typing import List, Optional

from app.core.brain.exceptions import MemoryAccessViolation
from app.core.brain.filesystem.protocol import DEFAULT_STRUCTURE, MemoryZone, get_zone_path

logger = logging.getLogger(__name__)

class BrainFileSystem:
    """
    Manages the file-based memory of the agent with strict path sandboxing.
    """
    
    def __init__(self, root_path: str):
        self.root = Path(root_path).resolve()
        
    def initialize(self):
        """Creates the directory structure if it doesn't exist."""
        if not self.root.exists():
            logger.info(f"Initializing Brain Memory at {self.root}")
            self.root.mkdir(parents=True, exist_ok=True)
            
        for zone, item in DEFAULT_STRUCTURE.items():
            zone_path = get_zone_path(self.root, zone)
            zone_path.mkdir(exist_ok=True)
            
            # Create default files if they are list of files (not dirs)
            # In protocol, some are files, some are dirs. 
            # For simplicity in this v1 manager, we just ensure zones exist.
            pass

    def _validate_path(self, path: str | Path) -> Path:
        """
        Ensures the path is strictly within the root directory.
        """
        # Resolve absolute path
        abs_path = (self.root / path).resolve()
        
        # Check against traversal attacks
        if not str(abs_path).startswith(str(self.root)):
            raise MemoryAccessViolation(f"Path access violation: {path}")
            
        return abs_path

    def read_file(self, path: str) -> str:
        """Reads a file from the memory."""
        target = self._validate_path(path)
        if not target.exists():
            return f"[Error: File not found: {path}]"
        
        if not target.is_file():
            return f"[Error: Not a file: {path}]"
            
        return target.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> str:
        """Writes content to a file. Overwrites if exists."""
        target = self._validate_path(path)
        
        # Ensure parent exists
        target.parent.mkdir(parents=True, exist_ok=True)
        
        target.write_text(content, encoding="utf-8")
        logger.debug(f"Memory Write: {path}")
        return f"Successfully wrote to {path}"
        
    def append_file(self, path: str, content: str) -> str:
        """Appends content to a file."""
        target = self._validate_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        
        with open(target, "a", encoding="utf-8") as f:
            f.write(content + "\n")
            
        return f"Successfully appended to {path}"

    def list_files(self, path: str = ".") -> List[str]:
        """Lists files in a directory."""
        target = self._validate_path(path)
        
        if not target.exists():
            return []
            
        if not target.is_dir():
            return [target.name]
            
        # Recursive list relative to root? No, just one level for now to be safe/simple
        results = []
        for item in target.iterdir():
            # Return path relative to root
            rel_path = item.relative_to(self.root)
            prefix = "[DIR] " if item.is_dir() else "[FILE]"
            results.append(f"{prefix} {rel_path}")
            
        return sorted(results)

    def search_files(self, query: str) -> List[str]:
        """
        Naive grep search across text files in memory.
        """
        results = []
        # Walk through all files
        for path in self.root.rglob("*.md"):
            try:
                content = path.read_text(encoding="utf-8")
                if query.lower() in content.lower():
                    rel_path = path.relative_to(self.root)
                    results.append(str(rel_path))
            except Exception:
                continue
                
        return results[:10]  # Limit results
