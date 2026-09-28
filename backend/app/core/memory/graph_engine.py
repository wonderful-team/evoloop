"""Graph backend stub — NOT implemented in this build."""

import logging

from app.core.memory.constants import DEFAULT_SEARCH_LIMIT
from app.core.memory.schemas import CheckpointDedupResult, StorageHealthCheck

logger = logging.getLogger(__name__)


class _GraphEngine:
    async def initialize(self) -> None:
        logger.warning(
            "[GraphEngine] Full mode (Neo4j) is not available in this build. "
            "Set EMBEDDED_MODE=True or implement the graph backend."
        )

    async def close(self) -> None:
        pass

    async def save(self, entry) -> None:
        raise NotImplementedError("GraphEngine is not available in this build.")

    async def get(self, entry_id: str):
        return None

    async def delete(self, entry_id: str) -> bool:
        return False

    async def search(self, query: str, **kwargs) -> list:
        return []

    async def list_all(
        self,
        type_filter=None,
        privacy_filter=None,
        project_id=None,
        limit=None,
        member_id=0,
    ) -> list:
        return []

    async def get_multi(self, entry_ids: list) -> dict:
        return {}

    async def find_episodes_by_concept(
        self, concept_name: str, limit: int = DEFAULT_SEARCH_LIMIT
    ) -> list:
        return []

    async def health_check(self):
        return StorageHealthCheck(status="not_available", backend="_GraphEngine (stub)")

    async def truncate_all(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def find_by_source_message_ids(self, message_ids: list) -> list:
        return []

    async def deduplicate_checkpoints(self, dry_run: bool = True):
        return CheckpointDedupResult(
            dry_run=dry_run,
            error="GraphEngine is a stub — not available in this build.",
        )
