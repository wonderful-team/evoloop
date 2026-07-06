"""
EpisodeReplay — loads recent episodes for dream distillation.

Queries the MemoryManager for recent EPISODE entries and formats them
as input for the LLM distillation prompt.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from app.core.memory.models import MemoryType

logger = logging.getLogger(__name__)


class EpisodeReplay:
    """Loads and formats recent episodes for Deep Dream replay."""

    def __init__(self, memory_manager: Any):
        self.manager = memory_manager

    async def load_recent_episodes(
        self,
        project_id: int | None = None,
        days_back: int = 7,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Load recent episode memories from the last N days.

        Args:
            project_id: Filter by project (None = all projects)
            days_back: How many days of history to replay
            limit: Max episodes to load

        Returns:
            List of episode dicts with id, goal, result, timestamp
        """
        try:
            results = await self.manager.search_memories(
                query="",
                types=[MemoryType.EPISODE],
                project_id=project_id,
                limit=limit,
            )
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning("[Dream:Replay] Failed to load episodes: %s", e)
            return []

        cutoff = datetime.now() - timedelta(days=days_back)
        episodes = []
        for entry in results:
            ts = entry.updated_at or entry.created_at
            if ts and isinstance(ts, datetime) and ts < cutoff:
                continue
            episodes.append({
                "id": entry.id,
                "goal": (entry.title or "").replace("Episode: ", ""),
                "result": entry.content or "",
                "description": entry.description or "",
                "timestamp": ts.isoformat() if ts else "",
                "project_id": entry.project_id,
                "source_message_id": entry.source_message_id,
            })

        logger.info("[Dream:Replay] Loaded %d episodes (days_back=%d)", len(episodes), days_back)
        return episodes

    def format_for_distillation(self, episodes: list[dict[str, Any]]) -> str:
        """
        Format episodes as markdown input for the LLM distillation prompt.

        Each episode is rendered as a numbered block with goal + outcome,
        so the LLM can identify cross-episode patterns.
        """
        if not episodes:
            return "(no episodes to replay)"

        lines = []
        for i, ep in enumerate(episodes, 1):
            lines.append(f"## Episode {i}")
            lines.append(f"**Goal**: {ep['goal']}")
            lines.append(f"**Outcome**: {ep['result'][:500]}")
            if ep.get("description") and ep["description"] != ep["result"][:200]:
                lines.append(f"**Summary**: {ep['description']}")
            lines.append("")

        return "\n".join(lines)
