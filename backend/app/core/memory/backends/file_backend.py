"""
File-based Memory Storage Backend - v2.0 Architecture

New structure:
~/.evoloop/memory/
├── journal/              # Agent work diary (date-based)
│   └── 2026-04-11.md
├── preferences/          # User preferences (long-term)
│   ├── coding-style.md
│   └── communication.md
├── context/              # Current project context (active)
│   └── project-43.md
├── decisions/            # Key decisions with rationale
│   └── 2026-04-11-recording-api.md
└── index/
    └── memory-map.json   # Memory index
"""

import logging
import time
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

from app.core.config import settings
from app.core.memory.models import (
    MemoryEntry,
    MemorySearchResult,
    MemoryType,
    PrivacyLevel,
)
from app.core.memory.interfaces.storage import IMemoryStorage, StorageError

logger = logging.getLogger(__name__)


class MemoryCategory(str, Enum):
    """Memory storage category - determines directory location."""
    JOURNAL = "journal"           # Daily work log
    PREFERENCES = "preferences"   # User preferences
    CONTEXT = "context"           # Active project context
    DECISIONS = "decisions"       # Key decisions with rationale


class FileMemoryStorage(IMemoryStorage):
    """
    File-based memory storage backend - v2.0

    Organized by purpose rather than privacy:
    - journal: Daily work records (Agent diary)
    - preferences: User preferences and feedback (long-term)
    - context: Active project working memory (frequently updated)
    - decisions: Key decisions with Why/How rationale
    """

    def __init__(self, root_path: Optional[str] = None):
        """
        Initialize file storage.

        Args:
            root_path: Root directory for memory storage.
                      Defaults to ~/.evoloop/memory
        """
        self.root = Path(root_path or settings.BRAIN_MEMORY_ROOT)
        self.journal_dir = self.root / "journal"
        self.preferences_dir = self.root / "preferences"
        self.context_dir = self.root / "context"
        self.decisions_dir = self.root / "decisions"
        self.index_dir = self.root / "index"
        self.index_file = self.index_dir / "memory-map.json"

        # ID -> (path, category) index for O(1) lookups
        self._id_index: Dict[str, tuple[Path, MemoryCategory]] = {}
        self._index_loaded = False

        # Ensure directories exist
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.preferences_dir.mkdir(parents=True, exist_ok=True)
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"FileMemoryStorage v2.0 initialized at {self.root}")

    def _load_id_index(self) -> None:
        """Build ID -> (Path, Category) index from all memory files."""
        if self._index_loaded:
            return

        start_time = time.time()
        self._id_index = {}
        count = 0

        for category in MemoryCategory:
            dir_path = self.root / category.value
            if not dir_path.exists():
                continue

            for path in dir_path.glob("*.md"):
                try:
                    # Read just the ID from frontmatter (fast path)
                    text = path.read_text(encoding="utf-8")
                    # Extract ID from first line of frontmatter
                    for line in text.split('\n')[:5]:
                        if line.startswith('id:'):
                            entry_id = line.split(':', 1)[1].strip()
                            self._id_index[entry_id] = (path, category)
                            count += 1
                            break
                except Exception:
                    continue

        self._index_loaded = True
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[FileStorage] ID index loaded: {count} entries in {elapsed:.1f}ms")

    def _get_storage_path(self, entry: MemoryEntry) -> tuple[Path, MemoryCategory]:
        """
        Determine storage path and category for a memory entry.

        Args:
            entry: Memory entry to store

        Returns:
            (Path, Category) where the entry should be stored
        """
        # Determine category based on type and tags
        category = self._determine_category(entry)
        base_dir = self.root / category.value

        # Generate filename based on entry properties
        if category == MemoryCategory.JOURNAL:
            # Journal entries by date
            date_str = entry.created_at.strftime("%Y-%m-%d")
            filename = f"{date_str}.md"
            # Journal is append-only, special handling needed
            return base_dir / filename, category

        elif category == MemoryCategory.DECISIONS:
            # Decisions by date + topic
            date_str = entry.created_at.strftime("%Y-%m-%d")
            topic = entry.tags[0] if entry.tags else "general"
            filename = f"{date_str}-{topic}.md"
            return base_dir / filename, category

        elif category == MemoryCategory.CONTEXT:
            # Context by project
            if entry.project_id:
                filename = f"project-{entry.project_id}.md"
            else:
                filename = f"{entry.id}.md"
            return base_dir / filename, category

        elif category == MemoryCategory.PREFERENCES:
            # Preferences by topic
            topic = entry.tags[0] if entry.tags else "general"
            filename = f"{topic}.md"
            return base_dir / filename, category

        # Default
        return base_dir / f"{entry.id}.md", category

    def _determine_category(self, entry: MemoryEntry) -> MemoryCategory:
        """Determine memory category from entry type and tags."""
        # Check tags first (highest priority)
        tag_set = set(t.lower() for t in entry.tags)

        if "journal" in tag_set or "diary" in tag_set or "daily" in tag_set:
            return MemoryCategory.JOURNAL

        if "preference" in tag_set or "feedback" in tag_set or "style" in tag_set:
            return MemoryCategory.PREFERENCES

        if "decision" in tag_set or "why" in tag_set or "rationale" in tag_set:
            return MemoryCategory.DECISIONS

        if "context" in tag_set or "active" in tag_set or "working" in tag_set:
            return MemoryCategory.CONTEXT

        # Fall back to type-based mapping
        if entry.type == MemoryType.USER:
            return MemoryCategory.PREFERENCES
        elif entry.type == MemoryType.FEEDBACK:
            return MemoryCategory.PREFERENCES
        elif entry.type == MemoryType.PROJECT:
            # Project memories could be context or decisions
            if entry.source == "checkpoint":
                return MemoryCategory.JOURNAL
            elif "decision" in entry.title.lower():
                return MemoryCategory.DECISIONS
            else:
                return MemoryCategory.CONTEXT
        elif entry.type == MemoryType.REFERENCE:
            return MemoryCategory.CONTEXT

        # Default to context
        return MemoryCategory.CONTEXT

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
        path, category = self._get_storage_path(entry)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Special handling for journal (append mode)
        if category == MemoryCategory.JOURNAL:
            await self._append_to_journal(entry, path)
        else:
            # Standard write (overwrite)
            entry.updated_at = datetime.utcnow()
            content = entry.to_frontmatter()
            path.write_text(content, encoding="utf-8")
            logger.info(f"Saved memory {entry.id} to {path}")

        # Update ID index for fast lookups
        self._update_id_index(entry.id, path, category)

        # Update JSON index
        await self._update_index(entry, path, category)

    async def _append_to_journal(self, entry: MemoryEntry, path: Path) -> None:
        """Append entry to journal file (special format)."""
        timestamp = entry.created_at.strftime("%H:%M")

        # Journal entry format (not frontmatter)
        journal_line = f"\n## [{timestamp}] {entry.title}\n\n{entry.content}\n\n---\n"

        if path.exists():
            with open(path, "a", encoding="utf-8") as f:
                f.write(journal_line)
        else:
            # Create new journal with header
            header = f"# {entry.created_at.strftime('%Y-%m-%d')}\n\n## 工作记录\n\n| 时间 | 项目 | 动作 | 结果 |\n|------|------|------|------|"
            path.write_text(header + journal_line, encoding="utf-8")

        logger.info(f"Appended journal entry {entry.id} to {path}")

    def _update_id_index(self, entry_id: str, path: Path, category: MemoryCategory) -> None:
        """Update ID index after save."""
        self._id_index[entry_id] = (path, category)

    def _remove_from_id_index(self, entry_id: str) -> None:
        """Remove from ID index after delete."""
        if entry_id in self._id_index:
            del self._id_index[entry_id]

    async def _update_index(self, entry: MemoryEntry, path: Path, category: MemoryCategory) -> None:
        """Update memory-map.json index."""
        try:
            index_data = {}
            if self.index_file.exists():
                with open(self.index_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)

            # Update index structure
            relative_path = self._get_relative_path(path)

            index_entry = {
                "id": entry.id,
                "title": entry.title,
                "description": entry.description[:100],
                "category": category.value,
                "path": relative_path,
                "tags": entry.tags,
                "updated_at": entry.updated_at.isoformat(),
            }

            # Store by ID for quick lookup
            if "entries" not in index_data:
                index_data["entries"] = {}

            index_data["entries"][entry.id] = index_entry

            # Update category lists
            if "categories" not in index_data:
                index_data["categories"] = {
                    "journal": [],
                    "preferences": [],
                    "context": [],
                    "decisions": [],
                }

            # Add to category list if not present
            cat_list = index_data["categories"][category.value]
            if entry.id not in cat_list:
                cat_list.append(entry.id)

            # Update metadata
            index_data["version"] = "2.0"
            index_data["last_updated"] = datetime.utcnow().isoformat()

            # Write back
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.warning(f"Failed to update index: {e}")

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get a memory entry by ID."""
        start_time = time.time()

        if not self._index_loaded:
            self._load_id_index()

        # O(1) lookup from index
        result = self._id_index.get(entry_id)
        if not result:
            # Index may be stale, try to rebuild
            self._load_id_index()
            result = self._id_index.get(entry_id)

        if result:
            path, category = result
            if path.exists():
                try:
                    text = path.read_text(encoding="utf-8")

                    # Special handling for journal (multi-entry file)
                    if category == MemoryCategory.JOURNAL:
                        entry = self._parse_journal_entry(text, entry_id, path)
                    else:
                        entry = MemoryEntry.from_frontmatter(text, str(path))

                    elapsed = (time.time() - start_time) * 1000
                    logger.debug(f"[FileStorage.get] Found {entry_id} in {elapsed:.1f}ms")
                    return entry
                except Exception as e:
                    logger.warning(f"[FileStorage.get] Failed to parse {path}: {e}")

        elapsed = (time.time() - start_time) * 1000
        logger.debug(f"[FileStorage.get] {entry_id} not found in {elapsed:.1f}ms")
        return None

    def _parse_journal_entry(self, text: str, entry_id: str, path: Path) -> Optional[MemoryEntry]:
        """Parse a specific entry from journal file."""
        # For now, return the whole journal as one entry
        # TODO: Parse individual sections by entry_id (timestamp)
        lines = text.split('\n')
        title = lines[0].replace("# ", "") if lines else "Journal"

        return MemoryEntry(
            id=entry_id,
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.PRIVATE,
            title=title,
            content=text,
            description=f"Journal entry from {title}",
            tags=["journal"],
            source="journal",
        )

    async def get_multi(self, entry_ids: List[str]) -> Dict[str, MemoryEntry]:
        """Get multiple memory entries by IDs."""
        results = {}

        for entry_id in entry_ids:
            entry = await self.get(entry_id)
            if entry:
                results[entry_id] = entry

        return results

    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        result = self._id_index.get(entry_id)
        if not result:
            # Try loading index
            self._load_id_index()
            result = self._id_index.get(entry_id)

        if result:
            path, category = result
            if path.exists():
                path.unlink()
                logger.info(f"Deleted memory {entry_id}")

                self._remove_from_id_index(entry_id)
                await self._remove_from_index(entry_id)
                return True

        return False

    async def _remove_from_index(self, entry_id: str) -> None:
        """Remove entry from JSON index."""
        try:
            if not self.index_file.exists():
                return

            with open(self.index_file, "r", encoding="utf-8") as f:
                index_data = json.load(f)

            if "entries" in index_data and entry_id in index_data["entries"]:
                entry = index_data["entries"].pop(entry_id)

                # Remove from category list
                category = entry.get("category")
                if category and "categories" in index_data:
                    cat_list = index_data["categories"].get(category, [])
                    if entry_id in cat_list:
                        cat_list.remove(entry_id)

            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.warning(f"Failed to remove from index: {e}")

    async def search(
        self,
        query: str,
        types: Optional[List[MemoryType]] = None,
        privacy: Optional[PrivacyLevel] = None,
        project_id: Optional[int] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """Search memory entries by text query."""
        results = []
        query_lower = query.lower()

        # Scan all categories
        for category in MemoryCategory:
            dir_path = self.root / category.value
            if not dir_path.exists():
                continue

            for path in dir_path.glob("*.md"):
                try:
                    text = path.read_text(encoding="utf-8")

                    # For journal, search differently
                    if category == MemoryCategory.JOURNAL:
                        if query_lower in text.lower():
                            # Return as journal entry
                            entry = self._parse_journal_entry(text, f"journal_{path.stem}", path)
                            results.append(entry)
                    else:
                        entry = MemoryEntry.from_frontmatter(text, str(path))

                        # Apply filters
                        if types and entry.type not in types:
                            continue
                        if privacy and entry.privacy != privacy:
                            continue
                        if project_id is not None and entry.project_id != project_id:
                            continue

                        # Text search
                        searchable = f"{entry.title} {entry.description} {entry.content}".lower()
                        if query_lower in searchable:
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
        limit: Optional[int] = None,
    ) -> List[MemorySearchResult]:
        """List all memory entries (lightweight)."""
        start_time = time.time()
        results = []

        # Try to use index first
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)

                for entry_id, entry_data in index_data.get("entries", {}).items():
                    results.append(MemorySearchResult(
                        id=entry_id,
                        type=MemoryType(entry_data.get("type", "project")),
                        title=entry_data.get("title", ""),
                        description=entry_data.get("description", ""),
                        created_at=datetime.fromisoformat(entry_data.get("updated_at", datetime.utcnow().isoformat())),
                        updated_at=datetime.fromisoformat(entry_data.get("updated_at", datetime.utcnow().isoformat())),
                    ))

                elapsed = (time.time() - start_time) * 1000
                logger.info(f"[FileStorage.list_all] {len(results)} entries from index in {elapsed:.1f}ms")
                return results[:limit] if limit else results

            except Exception as e:
                logger.warning(f"Failed to read index, falling back to scan: {e}")

        # Fallback: scan all files
        for category in MemoryCategory:
            dir_path = self.root / category.value
            if not dir_path.exists():
                continue

            for path in dir_path.glob("*.md"):
                try:
                    text = path.read_text(encoding="utf-8")
                    entry = MemoryEntry.from_frontmatter(text, str(path))

                    if type_filter and entry.type != type_filter:
                        continue
                    if privacy_filter and entry.privacy != privacy_filter:
                        continue

                    results.append(entry.to_search_result())
                except Exception as e:
                    logger.warning(f"Failed to read {path}: {e}")

        # Sort by updated_at descending
        results.sort(key=lambda x: x.updated_at, reverse=True)

        if limit:
            results = results[:limit]

        return results

    async def get_recent(self, count: int = 5) -> List[MemoryEntry]:
        """Get most recently updated memories."""
        results = []

        for category in MemoryCategory:
            dir_path = self.root / category.value
            if not dir_path.exists():
                continue

            for path in dir_path.glob("*.md"):
                try:
                    text = path.read_text(encoding="utf-8")
                    entry = MemoryEntry.from_frontmatter(text, str(path))
                    results.append(entry)
                except Exception as e:
                    logger.warning(f"Failed to read {path}: {e}")

        # Sort by updated_at descending
        results.sort(key=lambda x: x.updated_at, reverse=True)
        return results[:count]

    async def rebuild_index(self) -> None:
        """Rebuild entire memory-map.json index from scratch."""
        index_data = {
            "version": "2.0",
            "last_updated": datetime.utcnow().isoformat(),
            "entries": {},
            "categories": {
                "journal": [],
                "preferences": [],
                "context": [],
                "decisions": [],
            }
        }

        # Scan all categories
        for category in MemoryCategory:
            dir_path = self.root / category.value
            if not dir_path.exists():
                continue

            for path in dir_path.glob("*.md"):
                try:
                    text = path.read_text(encoding="utf-8")
                    entry = MemoryEntry.from_frontmatter(text, str(path))

                    relative_path = self._get_relative_path(path)

                    index_data["entries"][entry.id] = {
                        "id": entry.id,
                        "title": entry.title,
                        "description": entry.description[:100],
                        "category": category.value,
                        "path": relative_path,
                        "tags": entry.tags,
                        "updated_at": entry.updated_at.isoformat(),
                    }

                    index_data["categories"][category.value].append(entry.id)

                except Exception as e:
                    logger.warning(f"Failed to index {path}: {e}")

        # Write index
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Rebuilt memory index with {len(index_data['entries'])} entries")

    # ==========================================================================
    # IMemoryStorage Lifecycle Methods
    # ==========================================================================

    async def initialize(self) -> None:
        """Initialize file storage."""
        self._ensure_directories()
        logger.debug(f"FileMemoryStorage v2.0 initialized at {self.root}")

    async def close(self) -> None:
        """Close file storage."""
        logger.debug("FileMemoryStorage v2.0 closed")

    async def flush(self) -> None:
        """Clear all data (for testing)."""
        import shutil

        for category in MemoryCategory:
            dir_path = self.root / category.value
            if dir_path.exists():
                shutil.rmtree(dir_path)

        if self.index_file.exists():
            self.index_file.unlink()

        self._ensure_directories()
        logger.warning("FileMemoryStorage flushed (all data cleared)")

    async def deduplicate_checkpoints(self, dry_run: bool = True) -> Dict[str, Any]:
        """Remove duplicate checkpoint memories (not applicable in v2.0)."""
        # In v2.0, checkpoints are stored in journal by date
        # Duplicates are less likely, but we can scan journal files
        return {
            "dry_run": dry_run,
            "message": "Journal-based storage reduces duplication",
            "duplicates_found": 0,
            "duplicates_removed": 0,
        }

    async def find_by_source_message_ids(
        self,
        message_ids: list[str],
    ) -> list[MemoryEntry]:
        """Find memory entries by their source_message_id."""
        results = []
        message_id_set = set(message_ids)

        for category in MemoryCategory:
            dir_path = self.root / category.value
            if not dir_path.exists():
                continue

            for path in dir_path.glob("*.md"):
                try:
                    text = path.read_text(encoding="utf-8")
                    entry = MemoryEntry.from_frontmatter(text, str(path))

                    if entry.source_message_id and entry.source_message_id in message_id_set:
                        results.append(entry)
                except Exception as e:
                    logger.warning(f"Failed to read {path}: {e}")

        return results

    async def delete_by_source_message_ids(
        self,
        message_ids: list[str],
    ) -> int:
        """Delete memories linked to the given source message IDs."""
        entries = await self.find_by_source_message_ids(message_ids)
        count = 0

        for entry in entries:
            if await self.delete(entry.id):
                count += 1

        return count

    async def health_check(self) -> Dict[str, Any]:
        """Check storage health."""
        try:
            # Count entries per category
            category_counts = {}
            for category in MemoryCategory:
                dir_path = self.root / category.value
                if dir_path.exists():
                    count = len(list(dir_path.glob("*.md")))
                    category_counts[category.value] = count

            total = sum(category_counts.values())

            return {
                "status": "healthy",
                "backend": "FileMemoryStorage",
                "version": "2.0",
                "entry_count": total,
                "by_category": category_counts,
                "root_path": str(self.root),
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "backend": "FileMemoryStorage",
                "version": "2.0",
                "error": str(e),
            }


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
