"""Graph backend stub — NOT implemented in this build."""

import logging

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

    async def find_by_hash(self, content_hash: str, project_id=None):
        return None

    async def search(self, query: str, **kwargs) -> list:
        return []

    async def list_all(self, **kwargs) -> list:
        return []

    async def get_recent(self, count: int = 5, project_id=None) -> list:
        return []

    async def get_multi(self, entry_ids: list) -> dict:
        return {}

    async def search_similar(self, query_embedding: list, top_k: int = 10, project_id=None) -> list:
        return []

    async def get_related(self, entry_id: str, relation_type=None, limit: int = 10) -> list:
        return []

    async def link_concept_to_episode(self, concept_name: str, episode_id: str) -> None:
        pass

    async def find_episodes_by_concept(self, concept_name: str, limit: int = 10) -> list:
        return []

    async def get_all_concept_counts(self) -> dict:
        return {}

    async def health_check(self):
        return StorageHealthCheck(status="not_available", backend="_GraphEngine (stub)")

    async def truncate_all(self) -> None:
        pass

    async def flush(self) -> None:
        pass

    async def find_by_source_message_ids(self, message_ids: list) -> list:
        return []

    async def delete_by_source_message_ids(self, message_ids: list) -> int:
        return 0

    async def deduplicate_checkpoints(self, dry_run: bool = True):
        return CheckpointDedupResult(
            dry_run=dry_run,
            error="GraphEngine is a stub — not available in this build.",
        )
