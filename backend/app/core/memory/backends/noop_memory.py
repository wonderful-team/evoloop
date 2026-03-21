"""NoOp memory backends for embedded mode (no Neo4j required)."""

import logging
from typing import Any

from app.core.memory.interfaces.graph import IGraphNavigator
from app.core.memory.interfaces.long_term import (
    Concept,
    Episode,
    ILongTermMemory,
    SearchResult,
)
from app.core.memory.interfaces.preferences import IPreferenceStore

logger = logging.getLogger(__name__)


class NoOpLongTermMemory(ILongTermMemory):
    """NoOp implementation of long-term memory for embedded mode."""

    async def initialize(self) -> None:
        """No initialization needed."""
        logger.debug("NoOpLongTermMemory: Initialized")

    async def flush(self) -> None:
        """No flush needed."""
        logger.debug("NoOpLongTermMemory: Flushed")

    async def store_concept(self, concept: Concept) -> None:
        """No-op store concept."""
        logger.debug(f"NoOpLongTermMemory: store_concept skipped for '{concept.name}'")

    async def search_concepts(
        self, query: str, project_id: int | None = None, min_score: float = 0.7
    ) -> list[SearchResult]:
        """Return empty results."""
        logger.debug(f"NoOpLongTermMemory: search_concepts skipped for '{query}'")
        return []

    async def search_concepts_data(self, query: str, project_id: int | None = None) -> list[dict]:
        """Return empty results."""
        return []

    async def record_episode(self, episode: Episode) -> str | None:
        """No-op record episode."""
        goal_display = (episode.goal[:50] + "...") if episode.goal else "None"
        logger.debug(f"NoOpLongTermMemory: record_episode skipped for goal '{goal_display}'")
        return None

    async def retrieve_experience(self, goal: str, project_id: int, top_k: int = 3) -> str:
        """Return empty experience."""
        return ""

    async def link_episode_to_concepts(
        self, episode_id: str, concept_names: list[str], project_id: int
    ) -> None:
        """No-op link."""
        pass

    async def find_episodes_by_concept(
        self, concept_name: str, project_id: int, limit: int = 10
    ) -> list[dict]:
        """Return empty results."""
        return []

    async def list_concepts(self, project_id: int, limit: int = 50) -> list[dict]:
        """Return empty results."""
        return []

    async def get_project_concepts(self, project_id: int) -> list[str]:
        """Return empty results."""
        return []

    async def delete_episodes_by_message_ids(self, message_ids: list[str]) -> int:
        """No-op delete."""
        return 0

    async def delete_episodes_by_run_ids(self, run_ids: list[str]) -> int:
        """No-op delete."""
        return 0


class NoOpPreferenceStore(IPreferenceStore):
    """NoOp implementation of preference store for embedded mode."""

    async def initialize(self) -> None:
        """No initialization needed."""
        logger.debug("NoOpPreferenceStore: Initialized")

    async def flush(self) -> None:
        """No flush needed."""
        logger.debug("NoOpPreferenceStore: Flushed")

    async def set_preference(
        self,
        user_id: str,
        key: str,
        value: str,
        description: str = "",
        project_id: int | None = None,
    ) -> None:
        """No-op set preference."""
        logger.debug(f"NoOpPreferenceStore: set_preference skipped for key '{key}'")

    async def get_merged_preferences(self, user_id: str, project_id: int | None = None) -> str:
        """Return empty preferences."""
        return ""


class NoOpGraphNavigator(IGraphNavigator):
    """NoOp implementation of graph navigator for embedded mode."""

    async def initialize(self) -> None:
        """No initialization needed."""
        logger.debug("NoOpGraphNavigator: Initialized")

    async def flush(self) -> None:
        """No flush needed."""
        logger.debug("NoOpGraphNavigator: Flushed")

    async def get_node_details(self, node_type: str, filters: dict[str, Any]) -> dict:
        """Return empty details."""
        return {}

    async def traverse(
        self, start_node_id: str, relation_type: str, max_depth: int = 2
    ) -> list[dict[str, Any]]:
        """Return empty results."""
        return []

    async def get_directory_info(self, project_id: int, path: str) -> dict:
        """Return empty directory info."""
        return {"summary": "", "sub_modules": [], "dependencies": []}

    async def search(self, query: str, limit: int = 5) -> str:
        """Return empty search results."""
        return ""
