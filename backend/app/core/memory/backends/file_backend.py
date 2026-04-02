"""
File-based Long-term Memory Storage Backend

Unified file storage for embedded mode, inspired by Claude Code's memdir.
Supports both private and team memory directories.
"""

import logging
from pathlib import Path
from typing import List, Optional, Callable
from datetime import datetime
import fnmatch

from app.core.config import settings
from app.core.memory.models import (
    MemoryEntry,
    MemoryIndexEntry,
    MemorySearchResult,
    MemoryType,
    PrivacyLevel,
)

logger = logging.getLogger(__name__)


class FileMemoryStorage:
    """
    File-based memory storage backend.
    
    Storage structure:
    ~/.evoloop/memory/
    ├── MEMORY.md              # Index file
    ├── private/               # Private memories
    │   ├── user-profile.md
    │   ├── feedback/
    │   │   └── 2026-04-02-feedback-testing.md
    │   └── preferences.md
    └── team/                  # Team-shared memories
        ├── project-{id}/
        │   ├── architecture.md
        │   └── decisions.md
        └── reference/
            ├── libraries.md
            └── external-systems.md
    
    Inspired by Claude Code's memdir system.
    """
    
    def __init__(self, root_path: Optional[str] = None):
        """
        Initialize file storage.
        
        Args:
            root_path: Root directory for memory storage.
                      Defaults to settings.BRAIN_MEMORY_ROOT for compatibility.
        """
        self.root = Path(root_path or settings.BRAIN_MEMORY_ROOT)
        self.private_dir = self.root / "private"
        self.team_dir = self.root / "team"
        self.index_file = self.root / "MEMORY.md"
        
        # Ensure directories exist
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.private_dir.mkdir(parents=True, exist_ok=True)
        self.team_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for organization
        (self.private_dir / "feedback").mkdir(exist_ok=True)
        (self.team_dir / "reference").mkdir(exist_ok=True)
    
    def _get_storage_path(self, entry: MemoryEntry) -> Path:
        """
        Determine storage path for a memory entry.
        
        Args:
            entry: Memory entry to store
            
        Returns:
            Path where the entry should be stored
        """
        # Base directory based on privacy
        base = self.private_dir if entry.privacy == PrivacyLevel.PRIVATE else self.team_dir
        
        # Subdirectory based on type
        if entry.type == MemoryType.USER:
            # User profile goes in private root
            return base / f"{entry.id}.md"
        
        elif entry.type == MemoryType.FEEDBACK:
            # Feedback organized by date
            date_str = entry.created_at.strftime("%Y-%m-%d")
            subdir = base / "feedback"
            subdir.mkdir(exist_ok=True)
            return subdir / f"{date_str}-{entry.id}.md"
        
        elif entry.type == MemoryType.PROJECT:
            # Project memories organized by project_id
            if entry.project_id:
                subdir = base / f"project-{entry.project_id}"
            else:
                subdir = base / "project-global"
            subdir.mkdir(exist_ok=True)
            return subdir / f"{entry.id}.md"
        
        elif entry.type == MemoryType.REFERENCE:
            # Reference materials
            subdir = base / "reference"
            subdir.mkdir(exist_ok=True)
            return subdir / f"{entry.id}.md"
        
        # Default
        return base / f"{entry.id}.md"
    
    def _get_relative_path(self, full_path: Path) -> str:
        """Get path relative to root for indexing."""
        try:
            return str(full_path.relative_to(self.root))
        except ValueError:
            return str(full_path)
    
    async def save(self, entry: MemoryEntry) -> None:
        """
        Save a memory entry to file.
        
        Args:
            entry: Memory entry to save
        """
        path = self._get_storage_path(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Update timestamp
        entry.updated_at = datetime.utcnow()
        
        # Write file
        content = entry.to_frontmatter()
        path.write_text(content, encoding="utf-8")
        
        logger.info(f"Saved memory {entry.id} to {path}")
        
        # Update index
        await self._update_index(entry, path)
    
    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Get a memory entry by ID.
        
        Args:
            entry_id: Memory entry ID
            
        Returns:
            Memory entry or None if not found
        """
        # Search in all directories
        for pattern in ["**/*.md"]:
            for path in self.root.glob(pattern):
                if path.name == "MEMORY.md":
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                    entry = MemoryEntry.from_frontmatter(text, str(path))
                    if entry.id == entry_id:
                        return entry
                except Exception as e:
                    logger.warning(f"Failed to parse {path}: {e}")
                    continue
        
        return None
    
    async def delete(self, entry_id: str) -> bool:
        """
        Delete a memory entry.
        
        Args:
            entry_id: Memory entry ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        entry = await self.get(entry_id)
        if not entry:
            return False
        
        path = self._get_storage_path(entry)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted memory {entry_id}")
            
            # Update index to remove entry
            await self._remove_from_index(entry_id)
            return True
        
        return False
    
    async def search(
        self,
        query: str,
        types: Optional[List[MemoryType]] = None,
        privacy: Optional[PrivacyLevel] = None,
        project_id: Optional[int] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """
        Search memory entries by text query.
        
        Args:
            query: Search query text
            types: Filter by memory types
            privacy: Filter by privacy level
            project_id: Filter by project ID
            limit: Maximum number of results
            
        Returns:
            List of matching memory entries
        """
        results = []
        query_lower = query.lower()
        
        # Scan all memory files
        for pattern in ["private/**/*.md", "team/**/*.md"]:
            for path in self.root.glob(pattern):
                if path.name == "MEMORY.md":
                    continue
                
                try:
                    text = path.read_text(encoding="utf-8")
                    entry = MemoryEntry.from_frontmatter(text, str(path))
                    
                    # Apply filters
                    if types and entry.type not in types:
                        continue
                    if privacy and entry.privacy != privacy:
                        continue
                    if project_id is not None and entry.project_id != project_id:
                        continue
                    
                    # Text search (title, description, content)
                    searchable_text = f"{entry.title} {entry.description} {entry.content}".lower()
                    if query_lower in searchable_text:
                        results.append(entry)
                        
                        if len(results) >= limit:
                            return results
                            
                except Exception as e:
                    logger.warning(f"Failed to search {path}: {e}")
                    continue
        
        return results
    
    async def list_all(
        self,
        type_filter: Optional[MemoryType] = None,
        privacy_filter: Optional[PrivacyLevel] = None,
    ) -> List[MemorySearchResult]:
        """
        List all memory entries (lightweight, for indexing).
        
        Args:
            type_filter: Filter by type
            privacy_filter: Filter by privacy
            
        Returns:
            List of memory search results (without full content)
        """
        results = []
        
        for pattern in ["private/**/*.md", "team/**/*.md"]:
            for path in self.root.glob(pattern):
                if path.name == "MEMORY.md":
                    continue
                
                try:
                    # Read just the frontmatter for efficiency
                    text = path.read_text(encoding="utf-8")
                    entry = MemoryEntry.from_frontmatter(text, str(path))
                    
                    # Apply filters
                    if type_filter and entry.type != type_filter:
                        continue
                    if privacy_filter and entry.privacy != privacy_filter:
                        continue
                    
                    results.append(entry.to_search_result())
                    
                except Exception as e:
                    logger.warning(f"Failed to list {path}: {e}")
                    continue
        
        # Sort by updated_at descending
        results.sort(key=lambda x: x.updated_at, reverse=True)
        return results
    
    async def get_recent(self, count: int = 5) -> List[MemoryEntry]:
        """
        Get most recently updated memories.
        
        Args:
            count: Number of entries to return
            
        Returns:
            List of recent memory entries
        """
        entries = []
        
        for pattern in ["private/**/*.md", "team/**/*.md"]:
            for path in self.root.glob(pattern):
                if path.name == "MEMORY.md":
                    continue
                
                try:
                    text = path.read_text(encoding="utf-8")
                    entry = MemoryEntry.from_frontmatter(text, str(path))
                    entries.append(entry)
                except Exception as e:
                    logger.warning(f"Failed to read {path}: {e}")
                    continue
        
        # Sort by updated_at descending
        entries.sort(key=lambda x: x.updated_at, reverse=True)
        return entries[:count]
    
    async def _update_index(self, entry: MemoryEntry, path: Path) -> None:
        """
        Update MEMORY.md index file.
        
        Args:
            entry: Memory entry to add/update
            path: File path of the entry
        """
        relative_path = self._get_relative_path(path)
        index_entry = MemoryIndexEntry(
            title=entry.title,
            path=relative_path,
            description=entry.description[:100],
        )
        
        # Read existing index
        index_lines = []
        if self.index_file.exists():
            index_lines = self.index_file.read_text(encoding="utf-8").splitlines()
        
        # Check if entry already exists
        entry_line = index_entry.to_index_line()
        existing_idx = None
        for i, line in enumerate(index_lines):
            if f"]({relative_path})" in line:
                existing_idx = i
                break
        
        if existing_idx is not None:
            # Update existing entry
            index_lines[existing_idx] = entry_line
        else:
            # Add new entry at appropriate section
            section = self._get_section_for_type(entry.type)
            insert_idx = self._find_insert_position(index_lines, section)
            index_lines.insert(insert_idx, entry_line)
        
        # Write back
        self.index_file.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    
    async def _remove_from_index(self, entry_id: str) -> None:
        """Remove entry from index by ID."""
        if not self.index_file.exists():
            return
        
        # Find entry path from ID
        entry = await self.get(entry_id)
        if not entry:
            return
        
        path = self._get_storage_path(entry)
        relative_path = self._get_relative_path(path)
        
        # Remove from index
        index_lines = self.index_file.read_text(encoding="utf-8").splitlines()
        new_lines = [line for line in index_lines if f"]({relative_path})" not in line]
        
        self.index_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    
    def _get_section_for_type(self, mem_type: MemoryType) -> str:
        """Get index section name for memory type."""
        sections = {
            MemoryType.USER: "## User Profile",
            MemoryType.FEEDBACK: "## Feedback & Guidance",
            MemoryType.PROJECT: "## Project Context",
            MemoryType.REFERENCE: "## References",
        }
        return sections.get(mem_type, "## Other")
    
    def _find_insert_position(self, lines: List[str], section: str) -> int:
        """Find position to insert new index entry."""
        # Find section
        for i, line in enumerate(lines):
            if line.strip() == section:
                # Find end of section (next ## or end)
                for j in range(i + 1, len(lines)):
                    if lines[j].strip().startswith("## "):
                        return j
                return len(lines)
        
        # Section not found, add at end
        return len(lines)
    
    async def rebuild_index(self) -> None:
        """Rebuild entire MEMORY.md index from scratch."""
        sections = {
            "## User Profile": [],
            "## Feedback & Guidance": [],
            "## Project Context": [],
            "## References": [],
            "## Other": [],
        }
        
        # Scan all files
        all_entries = await self.list_all()
        
        for result in all_entries:
            # Get full entry
            entry = await self.get(result.id)
            if not entry:
                continue
            
            path = self._get_storage_path(entry)
            relative_path = self._get_relative_path(path)
            
            index_entry = MemoryIndexEntry(
                title=entry.title,
                path=relative_path,
                description=entry.description[:100],
            )
            
            section = self._get_section_for_type(entry.type)
            sections[section].append(index_entry.to_index_line())
        
        # Build index content
        lines = ["# Memory Index", ""]
        
        for section, entries in sections.items():
            if entries:
                lines.append(section)
                lines.append("")
                lines.extend(entries)
                lines.append("")
        
        # Write index
        self.index_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(f"Rebuilt memory index with {len(all_entries)} entries")


class MemoryStorageFactory:
    """Factory for creating memory storage backends."""
    
    @staticmethod
    def create_storage(backend_type: Optional[str] = None):
        """
        Create appropriate storage backend.
        
        Args:
            backend_type: 'file' or 'neo4j'. If None, auto-detect from settings.
            
        Returns:
            Storage backend instance
        """
        if backend_type is None:
            backend_type = "file" if settings.EMBEDDED_MODE else "neo4j"
        
        if backend_type == "file":
            return FileMemoryStorage()
        elif backend_type == "neo4j":
            # Import here to avoid dependency in embedded mode
            from app.core.memory.backends.neo4j_backend import Neo4jMemoryStorage
            return Neo4jMemoryStorage()
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")
