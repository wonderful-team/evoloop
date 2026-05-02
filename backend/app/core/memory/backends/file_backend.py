"""
File-based Memory Storage Backend - v2.1 Architecture (Hybrid)

This backend implements a high-performance hybrid storage strategy:
1. Markdown Files: The Source of Truth (SOT). Human-readable and persistent.
2. SQLite: Metadata index for O(log N) filtering and fast relational lookups.
3. LanceDB: Vector store for semantic similarity search.

All operations (save, delete, etc.) are orchestrated to maintain consistency across all three layers.
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

logger = logging.getLogger(__name__)


class MemoryCategory(str, Enum):
    """Memory storage category - determines directory location."""
    JOURNAL = "journal"  # Daily work log
    PREFERENCES = "preferences"  # User preferences
    CONTEXT = "context"  # Active project context
    DECISIONS = "decisions"  # Key decisions with rationale


class FileMemoryStorage(IMemoryStorage):
    """
    File-based memory storage backend - v2.1 (Hybrid)
    """

    def __init__(self, base_dir: str | None = None):
        """Initialize hybrid file storage."""
        self.root = Path(base_dir or settings.BRAIN_MEMORY_ROOT)
        self.journal_dir = self.root / "journal"
        self.preferences_dir = self.root / "preferences"
        self.context_dir = self.root / "context"
        self.decisions_dir = self.root / "decisions"
        self.index_dir = self.root / "index"
        
        # Backends
        from app.core.memory.backends.sqlite_index import SqliteMemoryIndex
        from app.core.memory.backends.vector_index import VectorMemoryIndex
        self.index_db = SqliteMemoryIndex(self.index_dir / "memory_metadata.db")
        self.vector_db = VectorMemoryIndex(self.index_dir / "vector_store")

        self._id_index: dict[str, tuple[Path, MemoryCategory]] = {}
        self._hash_index: dict[str, str] = {}  # hash -> id
        self._initialized = False
        self._lock = asyncio.Lock()

        # Ensure directories exist
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.preferences_dir.mkdir(parents=True, exist_ok=True)
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"FileMemoryStorage Hybrid directories ensured at {self.root}")

    async def initialize(self) -> None:
        """Initialize SQLite and Vector backends, and sync from disk if needed."""
        if self._initialized:
            return
            
        async with self._lock:
            if self._initialized:
                return
                
            await self.index_db.initialize()
            await self.vector_db.initialize()
            
            # Rebuild ID index in memory for fast path lookups
            await self._build_memory_id_index()
            
            # Sync check: if SQLite is empty but files exist, rebuild indices
            db_count = await self.index_db.get_count()
            if db_count == 0 and len(self._id_index) > 0:
                logger.info(f"[FileStorage] Index empty but {len(self._id_index)} files found. Rebuilding indices...")
                await self.rebuild_index()
                
            self._initialized = True
            logger.info(f"[FileStorage] Hybrid storage initialized (Entries: {len(self._id_index)})")

    async def close(self) -> None:
        """Release resources."""
        await self.index_db.close()
        await self.vector_db.close()
        self._initialized = False
        logger.debug("[FileStorage] Closed hybrid indices")

    async def _build_memory_id_index(self) -> None:
        """Build ID -> (Path, Category) mapping from disk for O(1) file retrieval."""
        start_time = time.time()
        
        loop = asyncio.get_event_loop()
        def _scan():
            id_idx = {}
            hash_idx = {}
            for category in MemoryCategory:
                dir_path = self.root / category.value
                if not dir_path.exists(): continue
                for path in dir_path.glob("*.md"):
                    try:
                        text = path.read_text(encoding="utf-8")
                        # Parse metadata only
                        entry = MemoryEntry.from_frontmatter(text, str(path))
                        id_idx[entry.id] = (path, category)
                        if entry.content_hash:
                            hash_idx[entry.content_hash] = entry.id
                    except Exception: continue
            return id_idx, hash_idx

        self._id_index, self._hash_index = await loop.run_in_executor(None, _scan)
        elapsed = (time.time() - start_time) * 1000
        logger.debug(f"[FileStorage] ID index built: {len(self._id_index)} entries in {elapsed:.1f}ms")

    async def rebuild_index(self) -> None:
        """Full rebuild of SQLite and Vector indices from Markdown files."""
        await self.index_db.clear()
        await self.vector_db.clear()
        
        for entry_id, (path, category) in self._id_index.items():
            try:
                text = path.read_text(encoding="utf-8")
                entry = MemoryEntry.from_frontmatter(text, str(path))
                
                # Update SQLite
                await self.index_db.upsert(entry, str(path))
                
                # Update Vector (skip journals to avoid cluttering semantic space)
                if category != MemoryCategory.JOURNAL:
                    await self.vector_db.add_entry(
                        entry.id, 
                        f"{entry.title}\n{entry.description}\n{entry.content}",
                        entry.project_id,
                        entry.user_id
                    )
            except Exception as e:
                logger.warning(f"Failed to index {path} during rebuild: {e}")

    def _get_storage_path(self, entry: MemoryEntry) -> tuple[Path, MemoryCategory]:
        """Determine physical storage path and logical category."""
        category = self._determine_category(entry)
        base_dir = self.root / category.value

        if category == MemoryCategory.JOURNAL:
            date_str = entry.created_at.strftime("%Y-%m-%d")
            return base_dir / f"{date_str}.md", category
        elif category == MemoryCategory.DECISIONS:
            date_str = entry.created_at.strftime("%Y-%m-%d")
            topic = entry.tags[0] if entry.tags else "general"
            return base_dir / f"{date_str}-{topic}.md", category
        elif category == MemoryCategory.CONTEXT:
            prefix = f"project-{entry.project_id}-" if entry.project_id else ""
            return base_dir / f"{prefix}{entry.id}.md", category
        elif category == MemoryCategory.PREFERENCES:
            topic = entry.tags[0] if entry.tags else "general"
            return base_dir / f"{topic}.md", category

        return base_dir / f"{entry.id}.md", category

    def _determine_category(self, entry: MemoryEntry) -> MemoryCategory:
        """Map entry metadata to a storage category."""
        tag_set = set(t.lower() for t in entry.tags)
        if any(t in tag_set for t in ["journal", "diary", "daily"]): return MemoryCategory.JOURNAL
        if any(t in tag_set for t in ["preference", "feedback", "style"]): return MemoryCategory.PREFERENCES
        if any(t in tag_set for t in ["decision", "why", "rationale"]): return MemoryCategory.DECISIONS
        if any(t in tag_set for t in ["context", "active", "working"]): return MemoryCategory.CONTEXT

        if entry.type in [MemoryType.USER, MemoryType.FEEDBACK]: return MemoryCategory.PREFERENCES
        if entry.type == MemoryType.PROJECT:
            if entry.source == "checkpoint": return MemoryCategory.JOURNAL
            return MemoryCategory.DECISIONS if "decision" in entry.title.lower() else MemoryCategory.CONTEXT
        return MemoryCategory.CONTEXT

    async def save(self, entry: MemoryEntry) -> None:
        """Save memory entry with write-through indexing across all layers."""
        if not self._initialized: await self.initialize()
        
        async with self._lock:
            if not entry.content_hash:
                entry.content_hash = MemoryEntry.compute_content_hash(entry.content)

            # Deduplication check
            if entry.content_hash in self._hash_index:
                existing_id = self._hash_index[entry.content_hash]
                if existing_id != entry.id:
                    logger.info(f"[FileStorage] Duplicate content hash {entry.content_hash[:8]} (ID: {existing_id}). Skipping.")
                    return

            path, category = self._get_storage_path(entry)
            path.parent.mkdir(parents=True, exist_ok=True)

            # 1. File Layer (SOT)
            if category == MemoryCategory.JOURNAL:
                await self._append_to_journal(entry, path)
            else:
                entry.updated_at = datetime.utcnow()
                content = entry.to_frontmatter()
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: path.write_text(content, encoding="utf-8"))

            # 2. Metadata Layer (SQL)
            self._id_index[entry.id] = (path, category)
            self._hash_index[entry.content_hash] = entry.id
            await self.index_db.upsert(entry, str(path))
            
            # 3. Vector Layer (LanceDB)
            if category != MemoryCategory.JOURNAL:
                await self.vector_db.add_entry(
                    memory_id=entry.id,
                    text=f"{entry.title}\n{entry.description}\n{entry.content}",
                    project_id=entry.project_id,
                    user_id=entry.user_id
                )
            
            logger.info(f"[FileStorage] Saved & Indexed {entry.id}")

    async def _append_to_journal(self, entry: MemoryEntry, path: Path) -> None:
        """Append entry to daily journal file."""
        timestamp = entry.created_at.strftime("%H:%M")
        journal_line = f"\n### [{timestamp}] {entry.title}\n{entry.content}\n"

        def _sync_append():
            mode = "a" if path.exists() else "w"
            with open(path, mode, encoding="utf-8") as f:
                if mode == "w":
                    f.write(f"# Journal {entry.created_at.strftime('%Y-%m-%d')}\n")
                f.write(journal_line)

        await asyncio.get_event_loop().run_in_executor(None, _sync_append)

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Fetch full memory entry from disk."""
        if not self._initialized: await self.initialize()
        
        target = self._id_index.get(entry_id)
        if not target:
            return None
        
        path, category = target
        if not path.exists():
            return None
        
        def _read():
            text = path.read_text(encoding="utf-8")
            return MemoryEntry.from_frontmatter(text, str(path))
            
        return await asyncio.get_event_loop().run_in_executor(None, _read)

    async def delete(self, entry_id: str) -> bool:
        """Atomic deletion from disk, SQL index, and Vector store."""
        if not self._initialized:
            await self.initialize()
        
        async with self._lock:
            target = self._id_index.get(entry_id)
            if not target:
                return False
            
            path, _ = target
            if path.exists():
                path.unlink()
            
            # Cleanup indices
            if entry_id in self._id_index: del self._id_index[entry_id]
            self._hash_index = {h: i for h, i in self._hash_index.items() if i != entry_id}
            
            await self.index_db.delete(entry_id)
            await self.vector_db.delete_entry(entry_id)
            
            logger.info(f"[FileStorage] Purged {entry_id} from all layers")
            return True

    async def search(
        self,
        query: str,
        types: list[MemoryType] | None = None,
        privacy: PrivacyLevel | None = None,
        project_id: int | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Hybrid search combining SQL metadata filtering and Vector semantic search."""
        if not self._initialized: await self.initialize()
        
        # 1. Metadata-only search (if query is empty)
        if not query:
            sql_filters = filters.copy() if filters else {}
            if project_id is not None: sql_filters["project_id"] = project_id
            if privacy: sql_filters["privacy"] = privacy.value
            
            if types:
                rows = []
                for t in types:
                    f = sql_filters.copy()
                    f["type"] = t.value
                    rows.extend(await self.index_db.search(f, limit=limit))
                rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                rows = rows[:limit]
            else:
                rows = await self.index_db.search(sql_filters, limit=limit)
            
            return [await self.get(row["id"]) for row in rows if row["id"]]

        # 2. Semantic Search (with vector-level filters)
        v_filters = {"project_id": project_id} if project_id is not None else {}
        if privacy: v_filters["privacy"] = privacy.value
        
        v_results = await self.vector_db.search(query, filters=v_filters, limit=limit * 3)
        
        # 3. Rehydrate and apply final filters
        results = []
        for v in v_results:
            if len(results) >= limit: break
            entry = await self.get(v["id"])
            if entry:
                if types and entry.type not in types: continue
                if filters:
                    if not all(getattr(entry, k, None) == val for k, val in filters.items()):
                        continue
                results.append(entry)
                
        return results

    async def list_all(
        self,
        type_filter: MemoryType | None = None,
        privacy_filter: PrivacyLevel | None = None,
        project_id: int | None = None,
        limit: int | None = None,
    ) -> list[MemorySearchResult]:
        """Fast metadata listing via SQLite index."""
        if not self._initialized: await self.initialize()
        
        sql_filters = {}
        if type_filter: sql_filters["type"] = type_filter.value
        if privacy_filter: sql_filters["privacy"] = privacy_filter.value
        if project_id is not None: sql_filters["project_id"] = project_id
        
        rows = await self.index_db.search(sql_filters, limit=limit or 1000)
        
        return [
            MemorySearchResult(
                id=row["id"],
                type=MemoryType(row["type"]),
                tier=MemoryTier(row["tier"]),
                utility_score=row["utility_score"],
                confidence=row["confidence"],
                title=row["title"],
                description=row["description"] or "",
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            ) for row in rows
        ]

    async def get_recent(self, count: int = 5, project_id: int | None = None) -> list[MemoryEntry]:
        """Get most recent entries via SQL index."""
        if not self._initialized: await self.initialize()
        
        filters = {"project_id": project_id} if project_id is not None else {}
        rows = await self.index_db.search(filters, limit=count)
        
        results = []
        for row in rows:
            entry = await self.get(row["id"])
            if entry: results.append(entry)
        return results

    async def find_by_hash(self, content_hash: str, project_id: Optional[int] = None) -> MemoryEntry | None:
        """Lookup memory by its content hash."""
        if not self._initialized: await self.initialize()
        
        entry_id = self._hash_index.get(content_hash)
        if not entry_id: return None
        
        entry = await self.get(entry_id)
        if entry and project_id is not None and entry.project_id != project_id:
            return None
        return entry

    async def get_multi(self, entry_ids: list[str]) -> dict[str, MemoryEntry]:
        """Batch fetch memories by ID."""
        results = {}
        for eid in entry_ids:
            e = await self.get(eid)
            if e: results[eid] = e
        return results

    async def find_by_source_message_ids(self, message_ids: list[str]) -> list[MemoryEntry]:
        """Find memories linked to specific message IDs via SQL index."""
        if not self._initialized: await self.initialize()
        
        results = []
        for mid in message_ids:
            rows = await self.index_db.search({"source_message_id": mid})
            for row in rows:
                e = await self.get(row["id"])
                if e: results.append(e)
        return results

    async def delete_by_source_message_ids(self, message_ids: list[str]) -> int:
        """Delete memories linked to given message IDs."""
        entries = await self.find_by_source_message_ids(message_ids)
        count = 0
        for e in entries:
            if await self.delete(e.id): count += 1
        return count

    async def health_check(self) -> StorageHealthCheck:
        """Check status of hybrid storage layers."""
        try:
            db_count = await self.index_db.get_count()
            return StorageHealthCheck(
                status="healthy",
                backend="FileMemoryStorage (Hybrid v2.1)",
                entry_count=db_count
            )
        except Exception as e:
            return StorageHealthCheck(status="unhealthy", backend="FileMemoryStorage (Hybrid)", error=str(e))

    async def deduplicate_checkpoints(self, dry_run: bool = True) -> CheckpointDedupResult:
        """Remove redundant snapshots, keeping only the most recent per thread."""
        results = await self.list_all(type_filter=MemoryType.PROJECT)
        checkpoints = [r for r in results if "checkpoint" in r.tags]
        
        if not checkpoints:
            return CheckpointDedupResult(dry_run=dry_run, total_checkpoints=0, duplicates_removed=0)

        from collections import defaultdict
        groups = defaultdict(list)
        for cp in checkpoints:
            thread_id = cp.id.split("_")[1] if "_" in cp.id else "general"
            groups[thread_id].append(cp)

        total_removed = 0
        for thread_id, group in groups.items():
            if len(group) <= 1: continue
            group.sort(key=lambda x: x.updated_at, reverse=True)
            for item in group[1:]:
                if not dry_run: await self.delete(item.id)
                total_removed += 1

        return CheckpointDedupResult(
            dry_run=dry_run,
            total_checkpoints=len(checkpoints),
            duplicate_groups=len(groups),
            duplicates_removed=total_removed
        )


class MemoryStorageFactory:
    """Factory for creating memory storage backends."""

    @staticmethod
    def create_storage(backend_type: str | None = None):
        """Create storage backend based on configuration."""
        if backend_type is None:
            backend_type = "file" if settings.EMBEDDED_MODE else "neo4j"
            
        if backend_type == "file":
            return FileMemoryStorage()
        elif backend_type == "neo4j":
            from app.core.memory.backends.neo4j_backend import Neo4jMemoryStorage
            return Neo4jMemoryStorage()
        else:
            raise ValueError(f"Unknown storage type: {backend_type}")
