"""Unified memory storage facade.

Delegates to _FileEngine (embedded mode) based on settings.EMBEDDED_MODE.
_GraphEngine is a stub — full Neo4j support is not implemented in this build.
"""

import logging
from typing import Any

from app.core.config import settings
from app.core.memory.constants import DEFAULT_SEARCH_LIMIT
from app.core.memory.file_engine import _FileEngine
from app.core.memory.graph_engine import _GraphEngine
from app.core.memory.models import MemoryEntry, MemorySearchResult, PrivacyLevel
from app.core.memory.schemas import CheckpointDedupResult, StorageHealthCheck

logger = logging.getLogger(__name__)


class MemoryStore:
    def __init__(
        self, base_dir: str | None = None, project_roots: dict[int, str] | None = None
    ):
        if settings.EMBEDDED_MODE:
            self._engine = _FileEngine(base_dir=base_dir, project_roots=project_roots)
        else:
            self._engine = _GraphEngine()

    def __getattr__(self, name: str):
        return getattr(self._engine, name)

    async def initialize(self) -> None:
        await self._engine.initialize()

    @property
    def project_roots(self) -> dict[int, str]:
        """Mutable mapping of project_id → project memory root path."""
        return self._engine._project_roots

    async def close(self) -> None:
        await self._engine.close()

    async def save(self, entry: MemoryEntry) -> None:
        if not settings.ENABLE_MEMORY:
            return
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
        types: list[Any] | None = None,
        privacy: PrivacyLevel | None = None,
        project_id: int | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        member_id: int | None = None,
    ) -> list[MemoryEntry]:
        return await self._engine.search(
            query=query,
            types=types,
            privacy=privacy,
            project_id=project_id,
            filters=filters,
            limit=limit,
            member_id=member_id,
        )

    async def list_all(
        self,
        type_filter: Any | None = None,
        privacy_filter: PrivacyLevel | None = None,
        project_id: int | None = None,
        limit: int | None = None,
        member_id: int = 0,
    ) -> list[MemorySearchResult]:
        return await self._engine.list_all(
            type_filter, privacy_filter, project_id, limit, member_id
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
        top_k: int = DEFAULT_SEARCH_LIMIT,
        project_id: int | None = None,
    ) -> list[MemoryEntry]:
        return await self._engine.search_similar(query_embedding, top_k, project_id)

    async def get_related(
        self,
        entry_id: str,
        relation_type: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[MemoryEntry]:
        return await self._engine.get_related(entry_id, relation_type, limit)

    async def link_concept_to_episode(self, concept_name: str, episode_id: str) -> None:
        await self._engine.link_concept_to_episode(concept_name, episode_id)

    async def find_episodes_by_concept(
        self, concept_name: str, limit: int = DEFAULT_SEARCH_LIMIT
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
