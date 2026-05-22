"""Unified memory storage facade.

Delegates to _FileEngine (embedded) or _GraphEngine (production) based on
settings.EMBEDDED_MODE.
"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional

import aiosqlite

from app.core.config import settings
from app.core.memory.models import (
    MemoryEntry,
    MemorySearchResult,
    MemoryTier,
    MemoryType,
    PrivacyLevel,
)
from app.core.memory.schemas import CheckpointDedupResult, StorageHealthCheck
from app.infrastructure.database.graph.driver import GraphManager
from app.infrastructure.database.vector import get_vector_store
from app.infrastructure.embeddings.factory import EmbedderFactory

logger = logging.getLogger(__name__)


class MemoryCategory(str, Enum):
    """Memory storage category - determines directory location."""

    JOURNAL = "journal"
    PREFERENCES = "preferences"
    CONTEXT = "context"
    DECISIONS = "decisions"


class _SQLiteIndexProxy:
    """Lightweight proxy exposing the raw SQLite layer for test compatibility."""

    __slots__ = ("_engine",)

    def __init__(self, engine: "_FileEngine"):
        self._engine = engine

    async def search(self, filters: dict, limit: int = 100) -> list[dict]:
        return await self._engine._sqlite_search(filters, limit)


class _FileEngine:
    """Embedded mode storage backed by Markdown SOT + SQLite + LanceDB."""

    def __init__(self, base_dir: str | None = None):
        self.root = Path(base_dir or settings.BRAIN_MEMORY_ROOT)
        self.journal_dir = self.root / "journal"
        self.preferences_dir = self.root / "preferences"
        self.context_dir = self.root / "context"
        self.decisions_dir = self.root / "decisions"
        self.index_dir = self.root / "index"

        self._db_path = self.index_dir / "memory_metadata.db"
        self._sqlite_initialized = False
        self._vector_store = get_vector_store()
        self.vector_db = self._vector_store  # alias for backward compatibility
        self.index_db = _SQLiteIndexProxy(self)
        self.__embedder = None

        self._id_index: dict[str, tuple[Path, MemoryCategory]] = {}
        self._hash_index: dict[str, str] = {}
        self._initialized = False
        self._lock = asyncio.Lock()

        self._ensure_directories()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_directories(self) -> None:
        for d in (
            self.journal_dir,
            self.preferences_dir,
            self.context_dir,
            self.decisions_dir,
            self.index_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def _embedder(self):
        if self.__embedder is None:
            try:
                self.__embedder = EmbedderFactory.get_embedder()
            except Exception as exc:
                logger.warning(f"[FileEngine] Failed to get embedder: {exc}")
                self.__embedder = None
        return self.__embedder

    async def _vector_add_entry(
        self,
        memory_id: str,
        text: str,
        project_id: int | None = None,
        user_id: str | None = None,
    ) -> None:
        embedder = self._embedder
        if embedder is None:
            return
        vector = await embedder.embed_query(text)
        if not vector:
            return
        record = {
            "id": memory_id,
            "vector": vector,
            "text": text,
            "project_id": project_id,
            "user_id": user_id or "",
        }
        self._vector_store.upsert_memory_chunks([record])

    async def _vector_delete_entry(self, memory_id: str) -> None:
        self._vector_store.delete_memory_by_id(memory_id)

    async def _vector_search(
        self, query: str, filters: dict[str, Any] | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        embedder = self._embedder
        if embedder is None:
            return []
        vector = await embedder.embed_query(query)
        if not vector:
            return []
        return self._vector_store.search_memory(
            query_vector=vector, top_k=limit, filters=filters
        )

    async def _build_memory_id_index(self) -> None:
        start_time = time.time()

        def _scan():
            id_idx: dict[str, tuple[Path, MemoryCategory]] = {}
            hash_idx: dict[str, str] = {}
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
                    except Exception as exc:
                        logger.debug(
                            f"[FileEngine] Skipping corrupted file {path.name}: {exc}"
                        )
                        continue
            return id_idx, hash_idx

        loop = asyncio.get_event_loop()
        self._id_index, self._hash_index = await loop.run_in_executor(None, _scan)
        elapsed = (time.time() - start_time) * 1000
        logger.debug(
            f"[FileEngine] ID index built: {len(self._id_index)} entries in {elapsed:.1f}ms"
        )

    async def _rebuild_index(self) -> None:
        await self._sqlite_clear()
        self._vector_store.delete_all_memories()
        for entry_id, (path, category) in self._id_index.items():
            try:
                text = path.read_text(encoding="utf-8")
                entry = MemoryEntry.from_frontmatter(text, str(path))
                await self._sqlite_upsert(entry, str(path))
                if category != MemoryCategory.JOURNAL:
                    await self._vector_add_entry(
                        entry.id,
                        f"{entry.title}\n{entry.description}\n{entry.content}",
                        entry.project_id,
                        entry.user_id,
                    )
            except Exception as exc:
                logger.warning(f"[FileEngine] Failed to index {path}: {exc}")

    def _determine_category(self, entry: MemoryEntry) -> MemoryCategory:
        tag_set = {t.lower() for t in entry.tags}
        if any(t in tag_set for t in ("journal", "diary", "daily")):
            return MemoryCategory.JOURNAL
        if any(t in tag_set for t in ("preference", "feedback", "style")):
            return MemoryCategory.PREFERENCES
        if any(t in tag_set for t in ("decision", "why", "rationale")):
            return MemoryCategory.DECISIONS
        if any(t in tag_set for t in ("context", "active", "working")):
            return MemoryCategory.CONTEXT

        if entry.type in (MemoryType.USER, MemoryType.FEEDBACK):
            return MemoryCategory.PREFERENCES
        if entry.type == MemoryType.PROJECT:
            if entry.source == "checkpoint":
                return MemoryCategory.JOURNAL
            return (
                MemoryCategory.DECISIONS
                if "decision" in entry.title.lower()
                else MemoryCategory.CONTEXT
            )
        return MemoryCategory.CONTEXT

    def _get_storage_path(self, entry: MemoryEntry) -> tuple[Path, MemoryCategory]:
        category = self._determine_category(entry)
        base_dir = self.root / category.value

        if category == MemoryCategory.JOURNAL:
            date_str = entry.created_at.strftime("%Y-%m-%d")
            return base_dir / f"{date_str}.md", category
        if category == MemoryCategory.DECISIONS:
            date_str = entry.created_at.strftime("%Y-%m-%d")
            topic = entry.tags[0] if entry.tags else "general"
            return base_dir / f"{date_str}-{topic}.md", category
        if category == MemoryCategory.CONTEXT:
            prefix = f"project-{entry.project_id}-" if entry.project_id else ""
            return base_dir / f"{prefix}{entry.id}.md", category
        if category == MemoryCategory.PREFERENCES:
            topic = entry.tags[0] if entry.tags else "general"
            return base_dir / f"{topic}.md", category

        return base_dir / f"{entry.id}.md", category

    async def _append_to_journal(self, entry: MemoryEntry, path: Path) -> None:
        timestamp = entry.created_at.strftime("%H:%M")
        journal_line = f"\n### [{timestamp}] {entry.title}\n{entry.content}\n"

        def _sync_append():
            mode = "a" if path.exists() else "w"
            with open(path, mode, encoding="utf-8") as f:
                if mode == "w":
                    f.write(f"# Journal {entry.created_at.strftime('%Y-%m-%d')}\n")
                f.write(journal_line)

        await asyncio.get_event_loop().run_in_executor(None, _sync_append)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await self._sqlite_initialize()
            await self._build_memory_id_index()
            db_count = await self._sqlite_get_count()
            if db_count == 0 and len(self._id_index) > 0:
                logger.info(
                    f"[FileEngine] Index empty but {len(self._id_index)} files found. Rebuilding..."
                )
                await self._rebuild_index()
            self._initialized = True
            logger.info(
                f"[FileEngine] Initialized ({len(self._id_index)} entries)"
            )

    async def close(self) -> None:
        self._sqlite_initialized = False
        self._initialized = False

    async def truncate_all(self) -> None:
        async with self._lock:
            for _eid, (path, _cat) in list(self._id_index.items()):
                if path.exists():
                    path.unlink()
            self._id_index.clear()
            self._hash_index.clear()
            await self._sqlite_clear()
            self._vector_store.delete_all_memories()
            logger.warning("[FileEngine] Truncated all data")

    async def flush(self) -> None:
        await self.truncate_all()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def save(self, entry: MemoryEntry) -> None:
        if not self._initialized:
            await self.initialize()
        async with self._lock:
            if not entry.content_hash:
                entry.content_hash = MemoryEntry.compute_content_hash(entry.content)

            if entry.content_hash in self._hash_index:
                existing_id = self._hash_index[entry.content_hash]
                if existing_id != entry.id:
                    logger.info(
                        f"[FileEngine] Duplicate hash {entry.content_hash[:8]} (ID: {existing_id}). Skipping."
                    )
                    return

            path, category = self._get_storage_path(entry)
            path.parent.mkdir(parents=True, exist_ok=True)

            if category == MemoryCategory.JOURNAL:
                await self._append_to_journal(entry, path)
            else:
                entry.updated_at = datetime.utcnow()
                content = entry.to_frontmatter()
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: path.write_text(content, encoding="utf-8")
                )

            self._id_index[entry.id] = (path, category)
            self._hash_index[entry.content_hash] = entry.id
            await self._sqlite_upsert(entry, str(path))

            if category != MemoryCategory.JOURNAL:
                await self._vector_add_entry(
                    entry.id,
                    f"{entry.title}\n{entry.description}\n{entry.content}",
                    entry.project_id,
                    entry.user_id,
                )

            logger.info(f"[FileEngine] Saved {entry.id}")

    async def get(self, entry_id: str) -> MemoryEntry | None:
        if not self._initialized:
            await self.initialize()
        target = self._id_index.get(entry_id)
        if not target:
            return None
        path, _category = target
        if not path.exists():
            return None

        def _read():
            text = path.read_text(encoding="utf-8")
            return MemoryEntry.from_frontmatter(text, str(path))

        return await asyncio.get_event_loop().run_in_executor(None, _read)

    async def delete(self, entry_id: str) -> bool:
        if not self._initialized:
            await self.initialize()
        async with self._lock:
            target = self._id_index.get(entry_id)
            if not target:
                return False
            path, _category = target
            if path.exists():
                path.unlink()
            self._id_index.pop(entry_id, None)
            self._hash_index = {
                h: i for h, i in self._hash_index.items() if i != entry_id
            }
            await self._sqlite_delete(entry_id)
            await self._vector_delete_entry(entry_id)
            logger.info(f"[FileEngine] Deleted {entry_id}")
            return True

    async def find_by_hash(
        self, content_hash: str, project_id: int | None = None
    ) -> MemoryEntry | None:
        if not self._initialized:
            await self.initialize()
        entry_id = self._hash_index.get(content_hash)
        if not entry_id:
            return None
        entry = await self.get(entry_id)
        if entry and project_id is not None and entry.project_id != project_id:
            return None
        return entry

    async def get_multi(self, entry_ids: list[str]) -> dict[str, MemoryEntry]:
        results: dict[str, MemoryEntry] = {}
        for eid in entry_ids:
            e = await self.get(eid)
            if e:
                results[eid] = e
        return results

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        types: list[MemoryType] | None = None,
        privacy: PrivacyLevel | None = None,
        project_id: int | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        if not self._initialized:
            await self.initialize()

        # Metadata-only search
        if not query:
            sql_filters = dict(filters) if filters else {}
            if project_id is not None:
                sql_filters["project_id"] = project_id
            if privacy:
                sql_filters["privacy"] = privacy.value

            if types:
                rows: list[dict] = []
                for t in types:
                    f = dict(sql_filters)
                    f["type"] = t.value
                    rows.extend(await self._sqlite_search(f, limit=limit))
                rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                rows = rows[:limit]
            else:
                rows = await self._sqlite_search(sql_filters, limit=limit)

            entries = [await self.get(row["id"]) for row in rows if row.get("id")]
            return [e for e in entries if e is not None]

        # Semantic search
        v_filters: dict[str, Any] = (
            {"project_id": project_id} if project_id is not None else {}
        )
        if privacy:
            v_filters["privacy"] = privacy.value

        v_results = await self._vector_search(query, filters=v_filters, limit=limit * 3)

        if not v_results:
            logger.debug("[FileEngine] Vector search unavailable, falling back to keyword")
            sql_filters = dict(filters) if filters else {}
            if project_id is not None:
                sql_filters["project_id"] = project_id
            if privacy:
                sql_filters["privacy"] = privacy.value

            type_values = [t.value for t in types] if types else []
            query_lower = query.lower()
            rows = await self._sqlite_search(sql_filters, limit=limit * 5)
            results: list[MemoryEntry] = []
            for row in rows:
                if len(results) >= limit:
                    break
                entry = await self.get(row["id"])
                if not entry:
                    continue
                if type_values and entry.type.value not in type_values:
                    continue
                text = f"{entry.title} {entry.description} {entry.content}".lower()
                if query_lower in text:
                    results.append(entry)
            return results

        results = []
        for v in v_results:
            if len(results) >= limit:
                break
            entry = await self.get(v.get("id"))
            if not entry:
                continue
            if types and entry.type not in types:
                continue
            if filters and not all(
                getattr(entry, k, None) == val for k, val in filters.items()
            ):
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
        if not self._initialized:
            await self.initialize()
        sql_filters: dict[str, Any] = {}
        if type_filter:
            sql_filters["type"] = type_filter.value
        if privacy_filter:
            sql_filters["privacy"] = privacy_filter.value
        if project_id is not None:
            sql_filters["project_id"] = project_id

        rows = await self._sqlite_search(sql_filters, limit=limit or 1000)
        return [
            MemorySearchResult(
                id=row["id"],
                type=MemoryType(row["type"]),
                tier=MemoryTier(row["tier"]),
                utility_score=row.get("utility_score", 0.0),
                confidence=row.get("confidence", 1.0),
                title=row["title"],
                description=row.get("description") or "",
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    async def get_recent(
        self, count: int = 5, project_id: int | None = None
    ) -> list[MemoryEntry]:
        if not self._initialized:
            await self.initialize()
        filters = {"project_id": project_id} if project_id is not None else {}
        rows = await self._sqlite_search(filters, limit=count)
        results: list[MemoryEntry] = []
        for row in rows:
            entry = await self.get(row["id"])
            if entry:
                results.append(entry)
        return results

    async def find_by_source_message_ids(
        self, message_ids: list[str]
    ) -> list[MemoryEntry]:
        if not self._initialized:
            await self.initialize()
        results: list[MemoryEntry] = []
        for mid in message_ids:
            rows = await self._sqlite_search({"source_message_id": mid})
            for row in rows:
                e = await self.get(row["id"])
                if e:
                    results.append(e)
        return results

    async def delete_by_source_message_ids(self, message_ids: list[str]) -> int:
        entries = await self.find_by_source_message_ids(message_ids)
        count = 0
        for e in entries:
            if await self.delete(e.id):
                count += 1
        return count

    async def health_check(self) -> StorageHealthCheck:
        try:
            db_count = await self._sqlite_get_count()
            return StorageHealthCheck(
                status="healthy",
                backend="_FileEngine (Hybrid)",
                entry_count=db_count,
            )
        except Exception as exc:
            return StorageHealthCheck(
                status="unhealthy", backend="_FileEngine (Hybrid)", error=str(exc)
            )

    async def deduplicate_checkpoints(
        self, dry_run: bool = True
    ) -> CheckpointDedupResult:
        candidates = await self.list_all(type_filter=MemoryType.PROJECT)
        checkpoints = []
        for c in candidates:
            entry = await self.get(c.id)
            if entry and "checkpoint" in entry.tags:
                checkpoints.append(entry)

        if not checkpoints:
            return CheckpointDedupResult(dry_run=dry_run, total_checkpoints=0, duplicates_removed=0)

        groups = defaultdict(list)
        for cp in checkpoints:
            parts = cp.id.split("_")
            thread_id = parts[1] if len(parts) > 1 else "general"
            groups[thread_id].append(cp)

        total_removed = 0
        for _thread_id, group in groups.items():
            if len(group) <= 1:
                continue
            group.sort(key=lambda x: x.updated_at, reverse=True)
            for item in group[1:]:
                if not dry_run:
                    await self.delete(item.id)
                total_removed += 1

        return CheckpointDedupResult(
            dry_run=dry_run,
            total_checkpoints=len(checkpoints),
            duplicate_groups=len(groups),
            duplicates_removed=total_removed,
        )

    # ------------------------------------------------------------------
    # Graph-specific no-ops / defaults
    # ------------------------------------------------------------------

    async def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        project_id: int | None = None,
    ) -> list[MemoryEntry]:
        return []

    async def get_related(
        self,
        entry_id: str,
        relation_type: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        return []

    async def link_concept_to_episode(
        self, concept_name: str, episode_id: str
    ) -> None:
        return

    async def find_episodes_by_concept(
        self, concept_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        return []

    async def get_all_concept_counts(self) -> dict[str, int]:
        return {}



    # ------------------------------------------------------------------
    # SQLite index methods (inlined from former SqliteMemoryIndex)
    # ------------------------------------------------------------------
    """
    SQLite-based index for memory metadata.
    Provides fast filtering and lookup for the file-based memory store.
    """

    async def _sqlite_initialize(self):
        """Create tables if they don't exist."""
        if self._sqlite_initialized:
            return

        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS memory_index (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    privacy TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    path TEXT NOT NULL,
                    project_id INTEGER,
                    user_id TEXT,
                    source TEXT,
                    source_message_id TEXT,
                    run_id TEXT,
                    content_hash TEXT,
                    confidence REAL,
                    utility_score REAL,
                    version INTEGER,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)

            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_project ON memory_index(project_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_user ON memory_index(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_run ON memory_index(run_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_msg ON memory_index(source_message_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_hash ON memory_index(content_hash)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mem_type ON memory_index(type)")

            await db.commit()

        self._sqlite_initialized = True
        logger.info(f"[_FileEngine|sqlite] Initialized at {self._db_path}")

    async def _sqlite_upsert(self, entry: MemoryEntry, file_path: str):
        """Insert or update a memory entry in the index."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO memory_index (
                    id, type, tier, privacy, title, description, path,
                    project_id, user_id, source, source_message_id, run_id,
                    content_hash, confidence, utility_score, version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id, entry.type.value, entry.tier.value, entry.privacy.value,
                entry.title, entry.description, str(file_path),
                entry.project_id, entry.user_id, entry.source,
                entry.source_message_id, entry.run_id,
                entry.content_hash, entry.confidence, entry.utility_score,
                entry.version, entry.created_at.isoformat(),
                entry.updated_at.isoformat()
            ))
            await db.commit()

    async def _sqlite_delete(self, entry_id: str) -> None:
        """Delete an entry from the index."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM memory_index WHERE id = ?", (entry_id,))
            await db.commit()

    async def _sqlite_close(self) -> None:
        """Close connection (no-op for connection-per-call pattern)."""
        self._sqlite_initialized = False
        logger.debug(f"[_FileEngine|sqlite] Closed (cleared initialized flag) for {self._db_path}")

    async def _sqlite_delete_by_run_id(self, run_id: str) -> int:
        """Delete all entries associated with a run_id."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM memory_index WHERE run_id = ?", (run_id,))
            count = cursor.rowcount
            await db.commit()
            return count

    async def _sqlite_delete_by_source_message_id(self, msg_id: str) -> int:
        """Delete all entries associated with a source_message_id."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM memory_index WHERE source_message_id = ?", (msg_id,))
            count = cursor.rowcount
            await db.commit()
            return count

    async def _sqlite_get_by_id(self, memory_id: str) -> Optional[dict]:
        """Get an entry's metadata by ID."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM memory_index WHERE id = ?", (memory_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def _sqlite_search(self, filters: dict, limit: int = 100) -> List[dict]:
        """Search for entries matching specific metadata filters."""
        query = "SELECT * FROM memory_index WHERE 1=1"
        params = []

        ALLOWED_COLUMNS = {
            "id", "type", "tier", "privacy", "title", "description", "path",
            "project_id", "user_id", "source", "source_message_id", "run_id",
            "content_hash", "confidence", "utility_score", "version",
            "created_at", "updated_at",
        }
        for key, value in filters.items():
            if value is not None and key in ALLOWED_COLUMNS:
                query += f" AND {key} = ?"
                params.append(value)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def _sqlite_list_all(self) -> List[dict]:
        """List all indexed metadata."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM memory_index") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def _sqlite_clear(self):
        """Wipe the entire index."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DELETE FROM memory_index")
            await db.commit()

    async def _sqlite_get_count(self) -> int:
        """Get total number of indexed entries."""
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM memory_index") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0


class _GraphEngine:
    """Production mode storage backed by a graph database (Neo4j)."""

    def __init__(self):
        self._driver: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        try:
            self._driver = GraphManager.get_driver()
            await self._driver.verify_connectivity()
            from app.infrastructure.database.graph.schema import schema_manager

            await schema_manager.initialize()
            logger.info("[GraphEngine] Initialized")
        except Exception as exc:
            raise ConnectionError(f"Failed to connect to graph: {exc}")

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("[GraphEngine] Closed")

    async def truncate_all(self) -> None:
        if not self._driver:
            return
        await self._driver.delete_nodes("Memory")
        await self._driver.delete_nodes("Concept")
        logger.warning("[GraphEngine] Truncated")

    async def flush(self) -> None:
        await self.truncate_all()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def save(self, entry: MemoryEntry) -> None:
        if not self._driver:
            raise RuntimeError("Graph driver not initialized")
        entry.updated_at = datetime.utcnow()
        label = "Concept" if entry.type == MemoryType.CONCEPT else "Memory"
        props = entry.model_dump()
        props["created_at"] = entry.created_at.isoformat()
        props["updated_at"] = entry.updated_at.isoformat()
        if props.get("extra"):
            props["extra"] = str(props["extra"])
        await self._driver.upsert_node(label, "id", props)
        logger.debug(f"[GraphEngine] Saved {entry.id} as {label}")

    async def get(self, entry_id: str) -> MemoryEntry | None:
        if not self._driver:
            raise RuntimeError("Graph driver not initialized")
        for label in ("Memory", "Concept"):
            nodes = await self._driver.find_nodes(label, {"id": entry_id}, limit=1)
            if nodes:
                return self._node_to_entry(nodes[0])
        return None

    async def find_by_hash(
        self, content_hash: str, project_id: int | None = None
    ) -> MemoryEntry | None:
        if not self._driver:
            raise RuntimeError("Graph driver not initialized")
        filters: dict[str, Any] = {"content_hash": content_hash}
        if project_id is not None:
            filters["project_id"] = project_id
        for label in ("Memory", "Concept"):
            nodes = await self._driver.find_nodes(label, filters, limit=1)
            if nodes:
                return self._node_to_entry(nodes[0])
        return None

    async def delete(self, entry_id: str) -> bool:
        if not self._driver:
            raise RuntimeError("Graph driver not initialized")
        deleted = await self._driver.delete_nodes("Memory", {"id": entry_id})
        if not deleted:
            deleted = await self._driver.delete_nodes("Concept", {"id": entry_id})
        return deleted > 0

    async def get_multi(self, entry_ids: list[str]) -> dict[str, MemoryEntry]:
        if not self._driver or not entry_ids:
            return {}
        results: dict[str, MemoryEntry] = {}
        for eid in entry_ids:
            entry = await self.get(eid)
            if entry:
                results[entry.id] = entry
        return results

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        types: list[MemoryType] | None = None,
        privacy: PrivacyLevel | None = None,
        project_id: int | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        if not self._driver:
            raise RuntimeError("Graph driver not initialized")
        all_results: list[MemoryEntry] = []
        for label in ("Memory", "Concept"):
            search_filters = dict(filters) if filters else {}
            if privacy:
                search_filters["privacy"] = privacy.value
            if project_id is not None:
                search_filters["project_id"] = project_id
            nodes = await self._driver.find_nodes(label, search_filters, limit=limit)
            for node in nodes:
                if query and query.lower() not in str(node).lower():
                    continue
                all_results.append(self._node_to_entry(node))
        return all_results[:limit]

    async def list_all(
        self,
        type_filter: MemoryType | None = None,
        privacy_filter: PrivacyLevel | None = None,
        project_id: int | None = None,
        limit: int | None = None,
    ) -> list[MemorySearchResult]:
        if not self._driver:
            raise RuntimeError("Graph driver not initialized")
        filters: dict[str, Any] = {}
        if type_filter:
            filters["type"] = type_filter.value
        if privacy_filter:
            filters["privacy"] = privacy_filter.value
        if project_id is not None:
            filters["project_id"] = project_id

        results: list[MemorySearchResult] = []
        for label in ("Memory", "Concept"):
            nodes = await self._driver.find_nodes(
                label, filters, limit=limit or 100
            )
            for node in nodes:
                entry = self._node_to_entry(node)
                if entry:
                    results.append(entry.to_search_result())
        return results[:limit] if limit else results

    async def get_recent(
        self, count: int = 5, project_id: int | None = None
    ) -> list[MemoryEntry]:
        if not self._driver:
            raise RuntimeError("Graph driver not initialized")
        all_entries: list[MemoryEntry] = []
        for label in ("Memory", "Concept"):
            filters: dict[str, Any] = {}
            if project_id is not None:
                filters["project_id"] = project_id
            nodes = await self._driver.find_nodes(label, filters, limit=count)
            all_entries.extend(
                self._node_to_entry(n) for n in nodes if n
            )
        all_entries.sort(key=lambda x: x.updated_at, reverse=True)
        return all_entries[:count]

    async def find_by_source_message_ids(
        self, message_ids: list[str]
    ) -> list[MemoryEntry]:
        if not self._driver:
            return []
        results: list[MemoryEntry] = []
        for mid in message_ids:
            for label in ("Memory", "Concept"):
                nodes = await self._driver.find_nodes(
                    label, {"source_message_id": mid}
                )
                for node in nodes:
                    entry = self._node_to_entry(node)
                    if entry:
                        results.append(entry)
        return results

    async def delete_by_source_message_ids(self, message_ids: list[str]) -> int:
        entries = await self.find_by_source_message_ids(message_ids)
        count = 0
        for e in entries:
            if await self.delete(e.id):
                count += 1
        return count

    async def health_check(self) -> StorageHealthCheck:
        if not self._driver:
            return StorageHealthCheck(
                status="not_initialized", backend="_GraphEngine"
            )
        try:
            nodes = await self._driver.find_nodes("Memory", limit=1)
            return StorageHealthCheck(
                status="healthy",
                backend="_GraphEngine",
                entry_count=len(nodes),
            )
        except Exception as exc:
            return StorageHealthCheck(
                status="unhealthy", backend="_GraphEngine", error=str(exc)
            )

    # ------------------------------------------------------------------
    # Graph-specific
    # ------------------------------------------------------------------

    async def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        project_id: int | None = None,
    ) -> list[MemoryEntry]:
        if not self._driver:
            return []
        filters = {"project_id": project_id} if project_id is not None else None
        nodes = await self._driver.search_similar(
            "Concept", query_embedding, top_k=top_k, filters=filters
        )
        return [self._node_to_entry(n) for n in nodes if n]

    async def get_related(
        self,
        entry_id: str,
        relation_type: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        if not self._driver:
            raise RuntimeError("Graph driver not initialized")
        nodes = await self._driver.traverse(
            "Memory",
            {"id": entry_id},
            rel_type=relation_type or "RELATED_TO",
            target_label="Memory",
            limit=limit,
        )
        return [self._node_to_entry(n) for n in nodes if n]

    async def link_concept_to_episode(
        self, concept_name: str, episode_id: str
    ) -> None:
        if not self._driver:
            return
        await self._driver.link_nodes(
            "Concept",
            {"title": concept_name},
            "Memory",
            {"id": episode_id},
            "LINKED_TO",
        )

    async def find_episodes_by_concept(
        self, concept_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        if not self._driver:
            return []
        nodes = await self._driver.traverse(
            "Concept",
            {"title": concept_name},
            rel_type="LINKED_TO",
            target_label="Memory",
            limit=limit,
        )
        return [
            {
                "id": n["id"],
                "goal": n["title"],
                "result": n["content"],
                "timestamp": n.get("created_at"),
            }
            for n in nodes
            if n
        ]

    async def get_all_concept_counts(self) -> dict[str, int]:
        if not self._driver:
            return {}
        query = """
        MATCH (c)-[:LINKED_TO]->(e:Memory)
        WHERE (c:Memory OR c:Concept) AND c.type = 'concept'
        RETURN c.title as name, count(e) as count
        """
        records = await self._driver.execute_query(query)
        return {r["name"]: r["count"] for r in records}

    async def deduplicate_checkpoints(
        self, dry_run: bool = True
    ) -> CheckpointDedupResult:
        return CheckpointDedupResult(dry_run=dry_run)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _node_to_entry(self, node: dict[str, Any]) -> MemoryEntry | None:
        try:
            return MemoryEntry(
                id=node["id"],
                type=MemoryType(node["type"]),
                privacy=PrivacyLevel(node["privacy"]),
                title=node["title"],
                content=node["content"],
                description=node.get("description", ""),
                project_id=node.get("project_id"),
                user_id=node.get("user_id"),
                tags=node.get("tags", []),
                source=node.get("source", "manual"),
                source_message_id=node.get("source_message_id"),
                confidence=node.get("confidence", 1.0),
                version=node.get("version", 1),
                created_at=datetime.fromisoformat(node["created_at"]),
                updated_at=datetime.fromisoformat(node["updated_at"]),
            )
        except Exception as exc:
            logger.warning(f"[GraphEngine] Failed to convert node: {exc}")
            return None


class MemoryStore:
    """Unified memory storage facade.

    Automatically selects the appropriate backend based on
    ``settings.EMBEDDED_MODE``.
    """

    def __init__(self, base_dir: str | None = None):
        if settings.EMBEDDED_MODE:
            self._engine = _FileEngine(base_dir=base_dir)
        else:
            self._engine = _GraphEngine()

    def __getattr__(self, name: str):
        """Transparently delegate attribute access to the underlying engine."""
        return getattr(self._engine, name)

    async def initialize(self) -> None:
        await self._engine.initialize()

    async def close(self) -> None:
        await self._engine.close()

    async def save(self, entry: MemoryEntry) -> None:
        await self._engine.save(entry)

    async def get(self, entry_id: str) -> MemoryEntry | None:
        return await self._engine.get(entry_id)

    async def delete(self, entry_id: str) -> bool:
        return await self._engine.delete(entry_id)

    async def find_by_hash(
        self, content_hash: str, project_id: int | None = None
    ) -> MemoryEntry | None:
        return await self._engine.find_by_hash(content_hash, project_id)

    async def search(
        self,
        query: str,
        types: list[MemoryType] | None = None,
        privacy: PrivacyLevel | None = None,
        project_id: int | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        return await self._engine.search(
            query, types, privacy, project_id, filters, limit
        )

    async def list_all(
        self,
        type_filter: MemoryType | None = None,
        privacy_filter: PrivacyLevel | None = None,
        project_id: int | None = None,
        limit: int | None = None,
    ) -> list[MemorySearchResult]:
        return await self._engine.list_all(
            type_filter, privacy_filter, project_id, limit
        )

    async def get_recent(
        self, count: int = 5, project_id: int | None = None
    ) -> list[MemoryEntry]:
        return await self._engine.get_recent(count, project_id)

    async def get_multi(self, entry_ids: list[str]) -> dict[str, MemoryEntry]:
        return await self._engine.get_multi(entry_ids)

    async def health_check(self) -> StorageHealthCheck:
        return await self._engine.health_check()

    async def find_by_source_message_ids(
        self, message_ids: list[str]
    ) -> list[MemoryEntry]:
        return await self._engine.find_by_source_message_ids(message_ids)

    async def delete_by_source_message_ids(self, message_ids: list[str]) -> int:
        return await self._engine.delete_by_source_message_ids(message_ids)

    async def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        project_id: int | None = None,
    ) -> list[MemoryEntry]:
        return await self._engine.search_similar(query_embedding, top_k, project_id)

    async def get_related(
        self,
        entry_id: str,
        relation_type: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        return await self._engine.get_related(entry_id, relation_type, limit)

    async def link_concept_to_episode(
        self, concept_name: str, episode_id: str
    ) -> None:
        await self._engine.link_concept_to_episode(concept_name, episode_id)

    async def find_episodes_by_concept(
        self, concept_name: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        return await self._engine.find_episodes_by_concept(concept_name, limit)

    async def get_all_concept_counts(self) -> dict[str, int]:
        return await self._engine.get_all_concept_counts()

    async def truncate_all(self) -> None:
        await self._engine.truncate_all()

    async def flush(self) -> None:
        await self._engine.flush()

    async def deduplicate_checkpoints(
        self, dry_run: bool = True
    ) -> CheckpointDedupResult:
        return await self._engine.deduplicate_checkpoints(dry_run)
