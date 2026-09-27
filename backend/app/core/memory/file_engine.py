"""File-backed memory engine — embedded mode storage backed by Markdown SOT + DB Index."""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select

from app.core.config import settings
from app.core.memory.constants import DEFAULT_SEARCH_LIMIT
from app.core.memory.models import (
    MemoryEntry,
    MemorySearchResult,
    MemoryTier,
    MemoryType,
    PrivacyLevel,
)
from app.core.memory.schemas import CheckpointDedupResult, StorageHealthCheck
from app.infrastructure.database import session_scope
from app.models.memory import MemoryIndex
from app.utils.time import elapsed_ms

logger = logging.getLogger(__name__)


class MemoryCategory(str, Enum):
    JOURNAL = "journal"
    PREFERENCES = "preferences"
    CONTEXT = "context"
    DECISIONS = "decisions"


class _FileEngine:
    def __init__(
        self, base_dir: str | None = None, project_roots: dict[int, str] | None = None
    ):
        self.root = Path(base_dir or settings.BRAIN_MEMORY_ROOT)
        self._project_roots: dict[int, Path] = {}
        if project_roots:
            self._project_roots = {pid: Path(p) for pid, p in project_roots.items()}
        self.journal_dir = self.root / "journal"
        self.preferences_dir = self.root / "preferences"
        self.context_dir = self.root / "context"
        self.decisions_dir = self.root / "decisions"
        self.index_dir = self.root / "index"

        self._db_initialized = True
        self._vector_store = None
        self.vector_db = None

        self._id_index: dict[str, tuple[Path, MemoryCategory]] = {}
        self._hash_index: dict[str, str] = {}
        self._initialized = False
        self._lock = asyncio.Lock()

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for d in (
            self.journal_dir,
            self.preferences_dir,
            self.context_dir,
            self.decisions_dir,
            self.index_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        # Ensure project memory directories exist
        for _pid, proj_root in self._project_roots.items():
            for cat in MemoryCategory:
                (Path(proj_root) / cat.value).mkdir(parents=True, exist_ok=True)

    async def _build_memory_id_index(self) -> None:
        start_time = time.time()

        def _scan_dir(dir_path: Path, id_idx: dict, hash_idx: dict) -> None:
            if not dir_path.exists():
                return
            for path in dir_path.glob("*.md"):
                try:
                    text = path.read_text(encoding="utf-8")
                    entry = MemoryEntry.from_frontmatter(text, str(path))
                    id_idx[entry.id] = (path, MemoryCategory(dir_path.name))
                    if entry.content_hash:
                        hash_idx[entry.content_hash] = entry.id
                except Exception as exc:
                    logger.debug(
                        f"[FileEngine] Skipping corrupted file {path.name}: {exc}",
                        exc_info=True,
                    )
                    continue

        def _scan():
            id_idx: dict[str, tuple[Path, MemoryCategory]] = {}
            hash_idx: dict[str, str] = {}
            for category in MemoryCategory:
                _scan_dir(self.root / category.value, id_idx, hash_idx)
            # Scan project-specific memory roots
            for proj_root in self._project_roots.values():
                for category in MemoryCategory:
                    _scan_dir(Path(proj_root) / category.value, id_idx, hash_idx)
            return id_idx, hash_idx

        loop = asyncio.get_running_loop()
        self._id_index, self._hash_index = await loop.run_in_executor(None, _scan)
        elapsed = elapsed_ms(start_time)
        logger.debug(
            f"[FileEngine] ID index built: {len(self._id_index)} entries in {elapsed:.1f}ms"
        )

    async def _rebuild_index(self) -> None:
        await self._db_clear()
        for _entry_id, (path, _category) in self._id_index.items():
            try:
                text = path.read_text(encoding="utf-8")
                entry = MemoryEntry.from_frontmatter(text, str(path))
                await self._db_upsert(entry, str(path))
            except Exception as exc:
                logger.warning(
                    f"[FileEngine] Failed to index {path}: {exc}", exc_info=True
                )

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

        # Route to project-specific directory if a project root is registered
        if (
            entry.project_id
            and entry.project_id > 0
            and entry.project_id in self._project_roots
        ):
            base_dir = self._project_roots[entry.project_id] / category.value

        if category == MemoryCategory.JOURNAL:
            date_str = entry.created_at.strftime("%Y-%m-%d")
            return base_dir / f"{date_str}.md", category
        if category == MemoryCategory.DECISIONS:
            date_str = entry.created_at.strftime("%Y-%m-%d")
            topic = entry.tags[0] if entry.tags else "general"
            return base_dir / f"{date_str}-{topic}.md", category
        if category == MemoryCategory.CONTEXT:
            user_prefix = f"user-{entry.member_id}-" if entry.member_id else ""
            prefix = f"project-{entry.project_id}-" if entry.project_id else ""
            return base_dir / f"{prefix}{user_prefix}{entry.id}.md", category
        if category == MemoryCategory.PREFERENCES:
            user_prefix = f"user-{entry.member_id}-" if entry.member_id else ""
            topic = entry.tags[0] if entry.tags else "general"
            return base_dir / f"{user_prefix}{topic}.md", category

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

        await asyncio.to_thread(_sync_append)

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await self._build_memory_id_index()
            db_count = await self._db_get_count()
            if db_count == 0 and len(self._id_index) > 0:
                logger.info(
                    f"[FileEngine] Index empty but {len(self._id_index)} files found. Rebuilding..."
                )
                await self._rebuild_index()
            self._initialized = True
            logger.info(f"[FileEngine] Initialized ({len(self._id_index)} entries)")

    async def close(self) -> None:
        self._db_initialized = False
        self._initialized = False

    async def truncate_all(self) -> None:
        async with self._lock:
            for _eid, (path, _cat) in list(self._id_index.items()):
                if path.exists():
                    path.unlink()
            self._id_index.clear()
            self._hash_index.clear()
            await self._db_clear()
            logger.warning("[FileEngine] Truncated all data")

    async def flush(self) -> None:
        await self.truncate_all()

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
                await asyncio.to_thread(path.write_text, content, encoding="utf-8")

            self._id_index[entry.id] = (path, category)
            self._hash_index[entry.content_hash] = entry.id
            await self._db_upsert(entry, str(path))

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

        return await asyncio.to_thread(_read)

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
            await self._db_delete(entry_id)
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

    async def search(
        self,
        query: str,
        types: list[MemoryType] | None = None,
        privacy: PrivacyLevel | None = None,
        project_id: int | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        member_id: int | None = None,
    ) -> list[MemoryEntry]:
        if not self._initialized:
            await self.initialize()

        sql_filters = dict(filters) if filters else {}
        if project_id is not None:
            sql_filters["project_id"] = project_id
        if privacy:
            sql_filters["privacy"] = privacy.value
        if member_id is not None:
            sql_filters["member_id"] = member_id

        if "member_id" not in sql_filters:
            try:
                from app.core.context.manager import ContextManager

                ctx = ContextManager.current()
                if ctx and ctx.member_id is not None:
                    sql_filters["member_id"] = ctx.member_id
            except Exception as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        if query:
            if types and len(types) == 1:
                sql_filters["type"] = types[0].value
            rows = await self._db_search(sql_filters, query=query, limit=limit * 5)
        else:
            if types:
                rows = []
                for t in types:
                    f = dict(sql_filters)
                    f["type"] = t.value
                    rows.extend(await self._db_search(f, limit=limit))
                rows.sort(
                    key=lambda x: x.get("created_at", datetime.min.isoformat()),
                    reverse=True,
                )
                rows = rows[:limit]
            else:
                rows = await self._db_search(sql_filters, limit=limit)

        entries = []
        for row in rows:
            if len(entries) >= limit:
                break
            entry = await self.get(row["id"])
            if not entry:
                continue
            if types and entry.type not in types:
                continue
            entries.append(entry)
        return entries

    async def list_all(
        self,
        type_filter: MemoryType | None = None,
        privacy_filter: PrivacyLevel | None = None,
        project_id: int | None = None,
        limit: int | None = None,
        member_id: int = 0,
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
        if member_id is not None:
            sql_filters["member_id"] = member_id

        rows = await self._db_search(sql_filters, limit=limit or 1000)

        results = []
        for row in rows:
            created = row["created_at"]
            if isinstance(created, str):
                created = datetime.fromisoformat(created)
            updated = row["updated_at"]
            if isinstance(updated, str):
                updated = datetime.fromisoformat(updated)
            results.append(
                MemorySearchResult(
                    id=row["id"],
                    type=MemoryType(row["type"]),
                    tier=MemoryTier(row["tier"]),
                    utility_score=row.get("utility_score", 0.0),
                    confidence=row.get("confidence", 1.0),
                    title=row["title"],
                    description=row.get("description") or "",
                    created_at=created,
                    updated_at=updated,
                )
            )
        return results

    async def get_recent(
        self, count: int = 5, project_id: int | None = None
    ) -> list[MemoryEntry]:
        if not self._initialized:
            await self.initialize()
        filters = {"project_id": project_id} if project_id is not None else {}
        rows = await self._db_search(filters, limit=count)
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
            rows = await self._db_search({"source_message_id": mid})
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
            db_count = await self._db_get_count()
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
            return CheckpointDedupResult(
                dry_run=dry_run, total_checkpoints=0, duplicates_removed=0
            )

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

    async def search_similar(
        self,
        query_embedding: list[float],
        top_k: int = DEFAULT_SEARCH_LIMIT,
        project_id: int | None = None,
    ) -> list[MemoryEntry]:
        return []

    async def get_related(
        self,
        entry_id: str,
        relation_type: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[MemoryEntry]:
        return []

    async def link_concept_to_episode(self, concept_name: str, episode_id: str) -> None:
        return

    async def find_episodes_by_concept(
        self, concept_name: str, limit: int = DEFAULT_SEARCH_LIMIT
    ) -> list[dict[str, Any]]:
        return []

    async def get_all_concept_counts(self) -> dict[str, int]:
        return {}

    async def _db_upsert(self, entry: MemoryEntry, file_path: str):
        async with session_scope() as session:
            stmt = select(MemoryIndex).where(MemoryIndex.id == entry.id)
            res = await session.execute(stmt)
            db_index = res.scalar_one_or_none()

            if not db_index:
                db_index = MemoryIndex(id=entry.id)
                session.add(db_index)

            db_index.type = entry.type.value
            db_index.tier = entry.tier.value
            db_index.privacy = entry.privacy.value
            db_index.title = entry.title
            db_index.description = entry.description
            db_index.path = str(file_path)
            db_index.project_id = entry.project_id
            db_index.member_id = entry.member_id
            db_index.source = entry.source
            db_index.source_message_id = entry.source_message_id

            db_index.source_file_path = entry.source_file_path
            db_index.source_thread_id = entry.source_thread_id
            db_index.source_message_id = (
                entry.source_message_id or entry.source_message_id
            )
            db_index.source_run_id = entry.run_id or entry.run_id
            db_index.source_wiki_title = entry.source_wiki_title

            db_index.content_hash = entry.content_hash
            db_index.confidence = entry.confidence
            db_index.utility_score = entry.utility_score
            db_index.version = entry.version
            db_index.created_at = entry.created_at
            db_index.updated_at = entry.updated_at

    async def _db_delete(self, entry_id: str) -> None:
        async with session_scope() as session:
            stmt = select(MemoryIndex).where(MemoryIndex.id == entry_id)
            res = await session.execute(stmt)
            db_index = res.scalar_one_or_none()
            if db_index:
                await session.delete(db_index)

    async def _db_delete_by_column(self, column, value: str) -> int:
        async with session_scope() as session:
            stmt = select(MemoryIndex).where(column == value)
            res = await session.execute(stmt)
            records = res.scalars().all()
            count = len(records)
            for r in records:
                await session.delete(r)
            return count

    async def _db_delete_by_source_thread_id(self, thread_id: str) -> int:
        return await self._db_delete_by_column(MemoryIndex.source_thread_id, thread_id)

    @staticmethod
    def _row_to_dict(row: MemoryIndex) -> dict:
        return {
            "id": row.id,
            "type": row.type,
            "tier": row.tier,
            "privacy": row.privacy,
            "title": row.title,
            "description": row.description,
            "path": row.path,
            "project_id": row.project_id,
            "member_id": row.member_id,
            "source": row.source,
            "source_message_id": row.source_message_id,
            "run_id": row.source_run_id,
            "source_file_path": row.source_file_path,
            "source_thread_id": row.source_thread_id,
            "source_wiki_title": row.source_wiki_title,
            "content_hash": row.content_hash,
            "confidence": row.confidence,
            "utility_score": row.utility_score,
            "version": row.version,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def _db_search(
        self, filters: dict, query: str | None = None, limit: int = 100
    ) -> list[dict]:
        async with session_scope() as session:
            stmt = select(MemoryIndex)
            for key, value in filters.items():
                if value is not None and hasattr(MemoryIndex, key):
                    stmt = stmt.where(getattr(MemoryIndex, key) == value)

            if query:
                words = query.strip().split()
                if words:
                    conditions = []
                    for word in words:
                        like_pat = f"%{word}%"
                        conditions.append(
                            (MemoryIndex.title.like(like_pat))
                            | (MemoryIndex.description.like(like_pat))
                        )
                    stmt = stmt.where(or_(*conditions))

            stmt = stmt.order_by(MemoryIndex.created_at.desc()).limit(limit)
            res = await session.execute(stmt)
            return [self._row_to_dict(row) for row in res.scalars().all()]

    async def _db_clear(self):
        async with session_scope() as session:
            stmt = select(MemoryIndex)
            res = await session.execute(stmt)
            for row in res.scalars().all():
                await session.delete(row)

    async def _db_get_count(self) -> int:
        async with session_scope() as session:
            stmt = select(func.count(MemoryIndex.id))
            res = await session.execute(stmt)
            return res.scalar() or 0
