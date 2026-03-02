"""
Memory System Mocks

Mock implementations for memory backends.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock


class MockShortTermMemory:
    """Mock implementation of short-term memory."""

    def __init__(self):
        self.messages: List[Dict] = []
        self.add_message = AsyncMock(side_effect=self._add_message)
        self.get_context = AsyncMock(side_effect=self._get_context)
        self.clear = AsyncMock(side_effect=self._clear)

    async def _add_message(self, thread_id: str, message: Any) -> None:
        self.messages.append({
            "thread_id": thread_id,
            "message": message,
        })

    async def _get_context(self, thread_id: str, limit: int = 50) -> List[Any]:
        return [
            m["message"] for m in self.messages
            if m["thread_id"] == thread_id
        ][-limit:]

    async def _clear(self, thread_id: str) -> None:
        self.messages = [
            m for m in self.messages
            if m["thread_id"] != thread_id
        ]


class MockLongTermMemory:
    """Mock implementation of long-term memory (Neo4j)."""

    def __init__(self):
        self.concepts: List[Dict] = []
        self.episodes: List[Dict] = []

        # Mock methods
        self.add_concept = AsyncMock(side_effect=self._add_concept)
        self.search_concepts = AsyncMock(side_effect=self._search_concepts)
        self.add_episode = AsyncMock(side_effect=self._add_episode)
        self.get_episodes = AsyncMock(side_effect=self._get_episodes)
        self.initialize = AsyncMock()

    async def _add_concept(
        self,
        name: str,
        description: str,
        project_id: int,
        **kwargs
    ) -> None:
        self.concepts.append({
            "name": name,
            "description": description,
            "project_id": project_id,
            **kwargs
        })

    async def _search_concepts(
        self,
        query: str,
        project_id: int,
        top_k: int = 5
    ) -> List[Dict]:
        # Simple keyword matching for testing
        return [
            c for c in self.concepts
            if query.lower() in c["name"].lower()
            or query.lower() in c["description"].lower()
        ][:top_k]

    async def _add_episode(
        self,
        goal: str,
        result: str,
        **kwargs
    ) -> None:
        self.episodes.append({
            "goal": goal,
            "result": result,
            **kwargs
        })

    async def _get_episodes(
        self,
        limit: int = 10,
        **filters
    ) -> List[Dict]:
        episodes = self.episodes

        # Apply simple filters
        for key, value in filters.items():
            episodes = [e for e in episodes if e.get(key) == value]

        return episodes[-limit:]
