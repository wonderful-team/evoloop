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

import asyncio
import json
import logging
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.core.memory.interfaces.storage import IMemoryStorage, StorageHealthCheck
from app.core.memory.models import (
    MemoryEntry,
    MemorySearchResult,
    MemoryTier,
    MemoryType,
    PrivacyLevel,
)
from app.core.memory.schemas import CheckpointDedupResult
from app.utils import render_template

logger = logging.getLogger(__name__)


class MemoryCategory(str, Enum):
    """Memory storage category - determines directory location."""
    JOURNAL = "journal"  # Daily work log
    PREFERENCES = "preferences"  # User preferences
    CONTEXT = "context"  # Active project context
    DECISIONS = "decisions"  # Key decisions with rationale


class FileMemoryStorage(IMemoryStorage):
    """
    File-based memory storage backend - v2.0

    Organized by purpose rather than privacy:
    - journal: Daily work records (Agent diary)
    - preferences: User preferences and feedback (long-term)
    - context: Active project working memory (frequently updated)
    - decisions: Key decisions with Why/How rationale
    """

    def __init__(self, base_dir: str | None = None):
        """
        Initialize file storage.

        Args:
            base_dir: Root directory for memory storage.
                      Defaults to ~/.evoloop/memory
        """
        self.root = Path(base_dir or settings.BRAIN_MEMORY_ROOT)
        self.journal_dir = self.root / "journal"
        self.preferences_dir = self.root / "preferences"
        self.context_dir = self.root / "context"
        self.decisions_dir = self.root / "decisions"
        self.index_dir = self.root / "index"
        self.index_file = self.index_dir / "memory-map.json"
        self.relations_file = self.index_dir / "relations.json"

        self._id_index: dict[str, tuple[Path, MemoryCategory]] = {}
        self._hash_index: dict[str, str] = {}  # hash -> id
        self._index_loaded = False
        self._lock = asyncio.Lock()

        # Ensure directories exist (fast, but we still favor initialize() for heavy work)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.preferences_dir.mkdir(parents=True, exist_ok=True)
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"FileMemoryStorage v2.0 initialized at {self.root}")

    async def _load_id_index(self) -> None:
        """Build ID -> (Path, Category) index from all memory files (Async)."""
        if self._index_loaded:
            return

        async with self._lock:
            # Re-check after lock
            if self._index_loaded:
                return

            loop = asyncio.get_event_loop()

            def _scan():
                start_time = time.time()
                id_idx = {}
                hash_idx = {}
                count = 0

                for category in MemoryCategory:
                    dir_path = self.root / category.value
                    if not dir_path.exists():
                        continue

                    for path in dir_path.glob("*.md"):
                        try:
                            text = path.read_text(encoding="utf-8")
                            entry = MemoryEntry.from_frontmatter(text, str(path))

                            id_idx[entry.id] = (path, category)
                            if entry.content_hash:
                                hash_idx[entry.content_hash] = entry.id
                            count += 1
                        except Exception as e:
                            logger.debug(f"[FileStorage] Failed to index {path}: {e}")
                            continue

                elapsed = (time.time() - start_time) * 1000
                return id_idx, hash_idx, count, elapsed

            self._id_index, self._hash_index, count, elapsed = await loop.run_in_executor(None, _scan)
            self._index_loaded = True
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
            # Context by project + ID to prevent overwriting
            if entry.project_id:
                filename = f"project-{entry.project_id}-{entry.id}.md"
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
        async with self._lock:
            # Re-check hash index inside the lock to prevent concurrent duplicates
            if not entry.content_hash:
                entry.content_hash = MemoryEntry.compute_content_hash(entry.content)

            if entry.content_hash in self._hash_index:
                existing_id = self._hash_index[entry.content_hash]
                if existing_id != entry.id:
                    logger.info(
                        f"[FileStorage] Memory with hash {entry.content_hash[:8]} already exists as {existing_id}. Skipping duplicate save for {entry.id}.")
                    return

            path, category = self._get_storage_path(entry)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Special handling for journal (append mode)
            if category == MemoryCategory.JOURNAL:
                await self._append_to_journal(entry, path)
            else:
                # Standard write (overwrite)
                entry.updated_at = datetime.utcnow()
                content = entry.to_frontmatter()
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: path.write_text(content, encoding="utf-8"))
                logger.info(f"[FileStorage] Saved memory {entry.id} (hash: {entry.content_hash[:8]}) to {path}")

            # Update ID index for fast lookups
            self._update_id_index(entry, path, category)

            # Update JSON index
            await self._update_index(entry, path, category)

    async def _append_to_journal(self, entry: MemoryEntry, path: Path) -> None:
        """Append entry to journal file (special format)."""
        timestamp = entry.created_at.strftime("%H:%M")
        journal_line = render_template(
            "core/memory/fragments/journal_entry.j2",
            timestamp=timestamp,
            title=entry.title,
            content=entry.content
        )

        def _sync_append():
            if path.exists():
                with open(path, "a", encoding="utf-8") as f:
                    f.write(journal_line)
            else:
                # Create new journal with header
                header = render_template(
                    "core/memory/fragments/journal_header.j2",
                    date=entry.created_at.strftime("%Y-%m-%d")
                )
                path.write_text(header + journal_line, encoding="utf-8")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_append)
        logger.info(f"Appended journal entry {entry.id} to {path}")

    def _update_id_index(self, entry: MemoryEntry, path: Path, category: MemoryCategory) -> None:
        """Update ID and Hash indices after save."""
        self._id_index[entry.id] = (path, category)
        if entry.content_hash:
            self._hash_index[entry.content_hash] = entry.id

    def _remove_from_id_index(self, entry_id: str) -> None:
        """Remove from indices after delete."""
        if entry_id in self._id_index:
            del self._id_index[entry_id]
            # Reverse lookup for hash if needed
            self._hash_index = {h: i for h, i in self._hash_index.items() if i != entry_id}

    async def _update_index(self, entry: MemoryEntry, path: Path, category: MemoryCategory) -> None:
        """Update memory-map.json index."""

        def _sync_update():
            try:
                index_data = {}
                if self.index_file.exists():
                    with open(self.index_file, encoding="utf-8") as f:
                        index_data = json.load(f)

                # Update index structure
                relative_path = self._get_relative_path(path)

                index_entry = {
                    "id": entry.id,
                    "title": entry.title,
                    "description": entry.description[:100],
                    "content_hash": entry.content_hash,
                    "category": category.value,
                    "path": relative_path,
                    "tags": entry.tags,
                    "tier": entry.tier.value,
                    "type": entry.type.value,
                    "privacy": entry.privacy.value,
                    "project_id": entry.project_id,
                    "user_id": entry.user_id,
                    "source_message_id": entry.source_message_id,
                    "utility_score": entry.utility_score,
                    "confidence": entry.confidence,
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

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_update)

    async def find_by_hash(self, content_hash: str, project_id: Optional[int] = None) -> MemoryEntry | None:
        """Find a memory entry by content hash for de-duplication."""
        if not self._index_loaded:
            await self._load_id_index()

        entry_id = self._hash_index.get(content_hash)
        if not entry_id:
            return None

        entry = await self.get(entry_id)
        if entry and project_id is not None and entry.project_id != project_id:
            return None
        return entry

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Get a memory entry by ID."""
        start_time = time.time()

        if not self._index_loaded:
            await self._load_id_index()

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
                    loop = asyncio.get_event_loop()

                    def _sync_get():
                        text = path.read_text(encoding="utf-8")
                        if category == MemoryCategory.JOURNAL:
                            return self._parse_journal_entry(text, entry_id, path)
                        return MemoryEntry.from_frontmatter(text, str(path))

                    entry = await loop.run_in_executor(None, _sync_get)
                except Exception as e:
                    logger.warning(f"[FileStorage.get] Failed to fetch {path}: {e}")
                    entry = None

                if entry:
                    elapsed = (time.time() - start_time) * 1000
                    logger.debug(f"[FileStorage.get] Found {entry_id} in {elapsed:.1f}ms")
                    return entry

        elapsed = (time.time() - start_time) * 1000
        logger.debug(f"[FileStorage.get] {entry_id} not found in {elapsed:.1f}ms")
        return None

    def _parse_journal_entry(self, text: str, entry_id: str, path: Path) -> MemoryEntry | None:
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

    async def get_multi(self, entry_ids: list[str]) -> dict[str, MemoryEntry]:
        """Get multiple memory entries by IDs."""
        results = {}

        for entry_id in entry_ids:
            entry = await self.get(entry_id)
            if entry:
                results[entry_id] = entry

        return results

    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        async with self._lock:
            result = self._id_index.get(entry_id)
            if not result:
                # Try loading index
                await self._load_id_index()
                result = self._id_index.get(entry_id)

            if result:
                path, category = result
                loop = asyncio.get_event_loop()

                def _sync_delete():
                    if path.exists():
                        path.unlink()
                        return True
                    return False

                deleted = await loop.run_in_executor(None, _sync_delete)
                if deleted:
                    logger.info(f"Deleted memory {entry_id}")
                    self._remove_from_id_index(entry_id)
                    await self._remove_from_index(entry_id)
                    return True

        return False

    async def _remove_from_index(self, entry_id: str) -> None:
        """Remove entry from JSON index."""

        def _sync_remove():
            try:
                if not self.index_file.exists():
                    return

                with open(self.index_file, encoding="utf-8") as f:
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

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _sync_remove)

    async def search(
        self,
        query: str,
        types: list[MemoryType] | None = None,
        privacy: PrivacyLevel | None = None,
        project_id: int | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Search memory entries using index-first strategy (O(1) metadata, O(K) content)."""
        query_lower = query.lower() if query else ""
        filters = filters or {}

        # 1. Performance optimization: specialized message search
        if not query and len(filters) == 1 and "source_message_id" in filters:
            msg_ids = filters["source_message_id"]
            if isinstance(msg_ids, str): msg_ids = [msg_ids]
            return await self.find_by_source_message_ids(msg_ids)

        # 2. Index-First Search
        def _sync_index_search():
            if not self.index_file.exists():
                return None, 0  # Fallback to scan if no index

            try:
                with open(self.index_file, encoding="utf-8") as f:
                    index_data = json.load(f)

                entries = index_data.get("entries", {})
                candidates = []

                type_vals = [t.value for t in types] if types else None
                privacy_val = privacy.value if privacy else None

                for eid, info in entries.items():
                    # Metadata Filtering (O(1) in index)
                    if type_vals and info.get("type") not in type_vals: continue
                    if privacy_val and info.get("privacy") != privacy_val: continue
                    if project_id is not None and info.get("project_id") != project_id: continue

                    # Custom Filters (support list values)
                    match_filters = True
                    for k, v in filters.items():
                        index_val = info.get(k)
                        if isinstance(v, (list, set, tuple)):
                            if index_val not in v:
                                match_filters = False
                                break
                        elif index_val != v:
                            match_filters = False
                            break
                    if not match_filters:
                        continue

                    # Text Search Pruning
                    # If query exists, try to match in index first (title/description)
                    priority = 0
                    if query_lower:
                        title_match = query_lower in info.get("title", "").lower()
                        desc_match = query_lower in info.get("description", "").lower()
                        tags_match = any(query_lower in t.lower() for t in info.get("tags", []))

                        if title_match:
                            priority = 3
                        elif desc_match:
                            priority = 2
                        elif tags_match:
                            priority = 1
                        else:
                            # Not in index metadata, must check content later
                            priority = -1

                    candidates.append(
                        (eid, info.get("path"), priority, info.get("updated_at", ""))
                    )

                # Sort by priority desc, then updated_at desc (newer first)
                candidates.sort(key=lambda x: (x[2], x[3] or ""), reverse=True)
                return candidates, len(entries)
            except Exception as e:
                logger.warning(f"Index search failed: {e}")
                return None, 0

        loop = asyncio.get_event_loop()
        candidates, total_entries = await loop.run_in_executor(None, _sync_index_search)

        # 3. Content-Level Verification (Only for candidates)
        results = []
        if candidates is not None:
            # We have indexed results. Now we only read files if:
            # a) We need the full MemoryEntry object (which we do)
            # b) We need to verify content match for priority -1 candidates

            for eid, rel_path, priority, _updated_at in candidates:
                if len(results) >= limit:
                    break

                # Load full entry from disk
                path = self.root / rel_path
                try:
                    def _read_and_verify():
                        if not path.exists(): return None
                        text = path.read_text(encoding="utf-8")

                        # Verify content match if it didn't match index metadata
                        if priority == -1:
                            if query_lower not in text.lower():
                                return None

                        # Check category-specific parsing (journal)
                        if "journal" in rel_path:
                            return self._parse_journal_entry(text, f"journal_{path.stem}", path)
                        return MemoryEntry.from_frontmatter(text, str(path))

                    entry = await loop.run_in_executor(None, _read_and_verify)
                    if entry:
                        results.append(entry)
                except Exception as e:
                    logger.debug(f"Failed to load candidate {eid}: {e}")

            logger.info(
                f"O(1) Search pruned {total_entries} down to {len(candidates)} candidates, loaded {len(results)}")
            return results

        # 4. Global Scan Fallback (if index failed or doesn't exist)
        logger.warning("Falling back to O(N) global scan search")
        # Reuse existing O(N) logic but wrapped in executor
        # (This is the logic we just refactored in previous turn)
        # For brevity, I'll keep the logic I just wrote above as the primary path.
        return await self._legacy_scan_search(query, types, privacy, project_id, filters, limit)

    async def _legacy_scan_search(self, query, types, privacy, project_id, filters, limit):
        """O(N) backup scan with full filter parity."""
        query_lower = query.lower() if query else ""
        type_vals = [t.value for t in types] if types else None
        privacy_val = privacy.value if privacy else None

        def _sync_scan():
            res = []
            for category in MemoryCategory:
                dir_path = self.root / category.value
                if not dir_path.exists(): continue
                for path in dir_path.glob("*.md"):
                    try:
                        text = path.read_text(encoding="utf-8")
                        entry = MemoryEntry.from_frontmatter(text, str(path))

                        # Apply all filters
                        if type_vals and entry.type.value not in type_vals: continue
                        if privacy_val and entry.privacy.value != privacy_val: continue
                        if project_id is not None and entry.project_id != project_id: continue

                        match_filters = True
                        for k, v in filters.items():
                            if getattr(entry, k, None) != v:
                                match_filters = False
                                break
                        if not match_filters: continue

                        if query_lower:
                            searchable = f"{entry.title} {entry.description} {entry.content}".lower()
                            if query_lower not in searchable: continue

                        res.append(entry)
                        if len(res) >= limit:
                            return res
                    except Exception:
                        continue
            return res

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_scan)

    async def list_all(
        self,
        type_filter: MemoryType | None = None,
        privacy_filter: PrivacyLevel | None = None,
        project_id: int | None = None,
        limit: int | None = None,
    ) -> list[MemorySearchResult]:
        """List memory entries (lightweight) with project and type filtering."""
        loop = asyncio.get_event_loop()

        def _sync_list():
            start_time = time.time()
            results = []

            # Try to use index first
            if self.index_file.exists():
                try:
                    with open(self.index_file, encoding="utf-8") as f:
                        index_data = json.load(f)

                    for entry_id, entry_data in index_data.get("entries", {}).items():
                        # Apply filters early (O(1) from index metadata)
                        if type_filter and entry_data.get("type") != type_filter.value:
                            continue

                        if privacy_filter and entry_data.get("privacy") != privacy_filter.value:
                            continue

                        entry_project_id = entry_data.get("project_id")
                        if project_id is not None and entry_project_id != project_id:
                            # Safely ignore ProjectMismatch
                            continue

                        results.append(MemorySearchResult(
                            id=entry_id,
                            type=MemoryType(entry_data.get("type", "project")),
                            tier=MemoryTier(entry_data.get("tier", "operational")),
                            utility_score=entry_data.get("utility_score", 0.0),
                            confidence=entry_data.get("confidence", 1.0),
                            title=entry_data.get("title", ""),
                            description=entry_data.get("description", ""),
                            created_at=datetime.fromisoformat(
                                entry_data.get("updated_at", datetime.utcnow().isoformat())),
                            updated_at=datetime.fromisoformat(
                                entry_data.get("updated_at", datetime.utcnow().isoformat())),
                        ))

                    elapsed = (time.time() - start_time) * 1000
                    logger.debug(f"[FileStorage.list_all] {len(results)} entries from index in {elapsed:.1f}ms")

                    results.sort(key=lambda x: x.updated_at, reverse=True)
                    return results[:limit] if limit else results
                except Exception as e:
                    logger.warning(f"Failed to read index: {e}")

            # Fallback scan... (omitted for brevity in sync nested def, but let's keep it complete)
            for category in MemoryCategory:
                dir_path = self.root / category.value
                if not dir_path.exists(): continue
                for path in dir_path.glob("*.md"):
                    try:
                        entry = MemoryEntry.from_frontmatter(path.read_text(encoding="utf-8"), str(path))
                        if type_filter and entry.type != type_filter: continue
                        if privacy_filter and entry.privacy != privacy_filter: continue
                        if project_id is not None and entry.project_id != project_id: continue
                        results.append(entry.to_search_result())
                    except Exception:
                        continue

            results.sort(key=lambda x: x.updated_at, reverse=True)
            return results[:limit] if limit else results

        # Run scan in executor
        results = await loop.run_in_executor(None, _sync_list)

        # CHAOS FIX: If index was missing, trigger background rebuild in the main loop
        if not self.index_file.exists():
            logger.info("[FileStorage] Index missing. Triggering background rebuild...")
            asyncio.create_task(self.rebuild_index())

        return results

    async def get_recent(self, count: int = 5, project_id: int | None = None) -> list[MemoryEntry]:
        """Get most recently updated memories (Index-backed, Non-blocking)."""
        if not self._index_loaded:
            await self._load_id_index()

        loop = asyncio.get_event_loop()

        def _sync_get_candidates():
            if not self.index_file.exists(): return []
            try:
                with open(self.index_file, encoding="utf-8") as f:
                    data = json.load(f)

                entries = list(data.get("entries", {}).values())
                # Filter by project
                if project_id is not None:
                    entries = [e for e in entries if e.get("project_id") == project_id]

                # Sort by updated_at descending
                entries.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
                return entries[:count]
            except Exception:
                return []

        candidates = await loop.run_in_executor(None, _sync_get_candidates)
        if not candidates:
            # Fallback: index missing — scan from storage and trigger rebuild
            logger.warning("[FileStorage] Index missing for get_recent. Scanning fallback...")
            asyncio.create_task(self.rebuild_index())
            summaries = await self.list_all(project_id=project_id, limit=count)
            if not summaries:
                return []
            entry_map = await self.get_multi([s.id for s in summaries])
            return list(entry_map.values())

        # Batch load full entries for candidates
        ids = [cand["id"] for cand in candidates]
        entry_map = await self.get_multi(ids)
        return list(entry_map.values())

    async def rebuild_index(self) -> None:
        """Rebuild entire memory-map.json index from scratch (Non-blocking)."""
        async with self._lock:
            def _sync_rebuild():
                index_data = {
                    "version": "2.1",  # Bump version for new fields
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
                    if not dir_path.exists(): continue
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
                                "tier": entry.tier.value,
                                "type": entry.type.value,
                                "privacy": entry.privacy.value,
                                "project_id": entry.project_id,
                                "user_id": entry.user_id,
                                "source_message_id": entry.source_message_id,
                                "utility_score": entry.utility_score,
                                "confidence": entry.confidence,
                                "updated_at": entry.updated_at.isoformat(),
                            }
                            index_data["categories"][category.value].append(entry.id)
                        except Exception as e:
                            logger.warning(f"Failed to index {path}: {e}")

                with open(self.index_file, "w", encoding="utf-8") as f:
                    json.dump(index_data, f, indent=2, ensure_ascii=False)
                return len(index_data['entries'])

            loop = asyncio.get_event_loop()
            count = await loop.run_in_executor(None, _sync_rebuild)
            logger.info(f"Rebuilt memory index with {count} entries")

    # ==========================================================================
    # Relationship Operations
    # ==========================================================================

    async def link_concept_to_episode(self, concept_name: str, episode_id: str) -> None:
        """Create a link between a concept and an episode in relations.json."""
        try:
            relations = {}
            if self.relations_file.exists():
                with open(self.relations_file, encoding="utf-8") as f:
                    relations = json.load(f)

            concept_links = relations.get(concept_name, [])
            if episode_id not in concept_links:
                concept_links.append(episode_id)
                relations[concept_name] = concept_links

                with open(self.relations_file, "w", encoding="utf-8") as f:
                    json.dump(relations, f, indent=2, ensure_ascii=False)
                logger.info(f"[FileStorage] Linked concept '{concept_name}' to episode {episode_id}")
        except Exception as e:
            logger.warning(f"Failed to link concept to episode: {e}")

    async def find_episodes_by_concept(self, concept_name: str, limit: int = 10) -> list[dict]:
        """Find all episodes linked to a specific concept."""
        if not self.relations_file.exists():
            return []

        try:
            with open(self.relations_file, encoding="utf-8") as f:
                relations = json.load(f)

            episode_ids = relations.get(concept_name, [])
            results = []

            for ep_id in reversed(episode_ids):  # Recent first
                if len(results) >= limit:
                    break

                entry = await self.get(ep_id)
                if entry:
                    # Return dict format matching EpisodeResponse
                    results.append({
                        "id": entry.id,
                        "goal": entry.title,  # Assuming title is the goal for episodes
                        "result": entry.content,
                        "timestamp": entry.created_at.isoformat()
                    })

            return results
        except Exception as e:
            logger.warning(f"Failed to find episodes by concept: {e}")
            return []

    async def get_all_concept_counts(self) -> dict[str, int]:
        """Efficiently count linked episodes for all concepts."""
        if not self.relations_file.exists():
            return {}
        try:
            with open(self.relations_file, encoding="utf-8") as f:
                relations = json.load(f)
            return {name: len(ep_ids) for name, ep_ids in relations.items()}
        except Exception as e:
            logger.warning(f"Failed to get concept counts: {e}")
            return {}

    # ==========================================================================
    # IMemoryStorage Lifecycle Methods
    # ==========================================================================

    async def initialize(self) -> None:
        """Initialize file storage (Non-blocking)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._ensure_directories)
        await self._load_id_index()

        # Check index version for migration
        if self.index_file.exists():
            try:
                def _check_version():
                    with open(self.index_file, encoding="utf-8") as f:
                        data = json.load(f)
                        return data.get("version", "1.0")

                version = await loop.run_in_executor(None, _check_version)
                if version < "2.1":
                    logger.info(f"Upgrading memory index from {version} to 2.1...")
                    await self.rebuild_index()
            except Exception as e:
                logger.warning(f"Failed to check index version: {e}")
                await self.rebuild_index()
        else:
            await self.rebuild_index()

        logger.debug(f"FileMemoryStorage initialized at {self.root}")

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

    async def deduplicate_checkpoints(self, dry_run: bool = True) -> "CheckpointDedupResult":
        """
        Remove duplicate checkpoint memories by keeping only the latest per thread.
        """
        from app.core.memory.manager import CheckpointDedupResult
        
        # 1. Collect all checkpoints
        results = await self.list_all(type_filter=MemoryType.PROJECT)
        checkpoints = [r for r in results if "checkpoint" in r.tags]
        
        if not checkpoints:
            return CheckpointDedupResult(dry_run=dry_run, message="No checkpoints found")

        # 2. Group by thread_id (extracting from tag or ID)
        from collections import defaultdict
        groups = defaultdict(list)
        
        for cp in checkpoints:
            # Checkpoints follow pattern: checkpoint_{thread_id}_{timestamp}
            parts = cp.id.split("_")
            if len(parts) >= 3 and parts[0] == "checkpoint":
                thread_id = parts[1]
                groups[thread_id].append(cp)
            else:
                # Fallback to general grouping if ID pattern doesn't match
                groups["general"].append(cp)

        total_removed = 0
        bytes_saved = 0
        processed_groups = 0

        # 3. Process groups: keep newest, remove others
        for thread_id, group in groups.items():
            if len(group) <= 1:
                continue
            
            processed_groups += 1
            # Sort newest first
            group.sort(key=lambda x: x.updated_at or x.created_at, reverse=True)
            
            # Keep index 0, delete others
            to_delete = group[1:]
            for item in to_delete:
                if not dry_run:
                    success = await self.delete(item.id)
                    if success:
                        total_removed += 1
                        # Estimate size if possible
                        bytes_saved += 500 # Approx min size
                else:
                    total_removed += 1

        return CheckpointDedupResult(
            dry_run=dry_run,
            total_checkpoints=len(checkpoints),
            duplicate_groups=processed_groups,
            duplicates_removed=total_removed,
            bytes_saved=bytes_saved,
            message="Successfully deduplicated thread snapshots"
        )

    async def find_by_source_message_ids(self, message_ids: list[str]) -> list[MemoryEntry]:
        """Find memory entries by their source_message_id (Index-backed, O(1))."""
        if not self._index_loaded:
            await self._load_id_index()

        message_id_set = set(message_ids)
        loop = asyncio.get_event_loop()

        def _sync_index_lookup():
            if not self.index_file.exists(): return None
            try:
                with open(self.index_file, encoding="utf-8") as f:
                    data = json.load(f)

                candidate_ids = []
                for eid, info in data.get("entries", {}).items():
                    if info.get("source_message_id") in message_id_set:
                        candidate_ids.append(eid)
                return candidate_ids
            except Exception:
                return None

        candidate_ids = await loop.run_in_executor(None, _sync_index_lookup)

        if candidate_ids is not None:
            # Batch fetch from storage
            entry_map = await self.get_multi(candidate_ids)
            return list(entry_map.values())

        # Fallback to scan only if index lookup fails
        def _sync_fallback_find():
            local_results = []
            for category in MemoryCategory:
                dir_path = self.root / category.value
                if not dir_path.exists(): continue
                for path in dir_path.glob("*.md"):
                    try:
                        text = path.read_text(encoding="utf-8")
                        entry = MemoryEntry.from_frontmatter(text, str(path))
                        if entry.source_message_id and entry.source_message_id in message_id_set:
                            local_results.append(entry)
                    except Exception:
                        continue
            return local_results

        return await loop.run_in_executor(None, _sync_fallback_find)

    async def delete_by_source_message_ids(self, message_ids: list[str]) -> int:
        """Delete memories linked to the given source message IDs."""
        entries = await self.find_by_source_message_ids(message_ids)
        count = 0

        for entry in entries:
            if await self.delete(entry.id):
                count += 1

        return count

    async def health_check(self) -> "StorageHealthCheck":
        """Check storage health."""
        try:
            # Count entries per category (Async)
            category_counts = {}

            def _sync_counts():
                counts = {}
                for category in MemoryCategory:
                    dir_path = self.root / category.value
                    if dir_path.exists():
                        counts[category.value] = len(list(dir_path.glob("*.md")))
                    else:
                        counts[category.value] = 0
                return counts

            loop = asyncio.get_event_loop()
            category_counts = await loop.run_in_executor(None, _sync_counts)

            total = sum(category_counts.values())

            return StorageHealthCheck(
                status="healthy",
                backend="FileMemoryStorage",
                version="2.0",
                entry_count=total,
                by_category=category_counts,
                root_path=str(self.root),
            )
        except Exception as e:
            return StorageHealthCheck(
                status="unhealthy",
                backend="FileMemoryStorage",
                version="2.0",
                error=str(e),
            )


class MemoryStorageFactory:
    """Factory for creating memory storage backends."""

    @staticmethod
    def create_storage(backend_type: str | None = None):
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
