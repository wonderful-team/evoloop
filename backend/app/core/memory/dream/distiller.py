"""
DeepDreamDistiller — LLM-based episode-to-insight distillation.

Replays recent episodes and asks the LLM to extract reusable knowledge:
patterns, gotchas, architectural decisions, and techniques. The extracted
insights are stored as strategic CONCEPT entries in long-term memory.

This is the "dream" — the agent reflecting on its experiences to learn.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any

from app.core.memory.models import MemoryEntry, MemoryTier, MemoryType, PrivacyLevel
from app.utils.template import render_template

from .replay import EpisodeReplay
from .schemas import DreamInsight, DreamResult

logger = logging.getLogger(__name__)


class DeepDreamDistiller:
    """Distills insights from episode replay via LLM."""

    def __init__(self, memory_manager: Any):
        self.manager = memory_manager
        self.replay = EpisodeReplay(memory_manager)

    async def dream(
        self,
        project_id: int | None = None,
        days_back: int = 7,
        max_episodes: int = 20,
    ) -> DreamResult:
        """
        Run a single dream cycle.

        1. Load recent episodes
        2. Format for LLM
        3. Invoke LLM to extract insights
        4. Store insights as CONCEPT entries
        5. Regenerate hot memory (MEMORY.md)

        Returns:
            DreamResult with stats and generated insight IDs
        """
        result = DreamResult(started_at=datetime.now())

        # 1. Load episodes
        episodes = await self.replay.load_recent_episodes(
            project_id=project_id,
            days_back=days_back,
            limit=max_episodes,
        )
        result.episodes_replayed = len(episodes)

        if len(episodes) < 2:
            logger.info("[Dream] Skipping: only %d episodes (need >= 2)", len(episodes))
            result.finished_at = datetime.now()
            return result

        # 2. Format for LLM
        episodes_text = self.replay.format_for_distillation(episodes)

        # 2b. Deduplication Check
        import hashlib
        from pathlib import Path

        from app.core.config import settings
        episodes_hash = hashlib.md5(episodes_text.encode("utf-8")).hexdigest()
        
        # Resolve hash file path
        hash_file_name = f".last_dream_hash_{project_id or 'global'}"
        hash_file_dir = Path(settings.APP_DATA_DIR) / "memory"
        hash_file_path = hash_file_dir / hash_file_name
        
        # Read last hash
        last_hash = ""
        if hash_file_path.exists():
            try:
                last_hash = hash_file_path.read_text(encoding="utf-8").strip()
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.warning("[Dream] Failed to read last dream hash file: %s", e)

        if episodes_hash == last_hash:
            logger.info("[Dream] Skipping: No new episodes or identical content since last dream cycle")
            result.finished_at = datetime.now()
            return result

        # 3. Invoke LLM
        insights = await self._distill(episodes_text, episodes)
        result.insights_generated = insights

        # 4. Store insights
        for insight in insights:
            entry_id = await self._store_insight(insight, project_id)
            if entry_id:
                result.insight_ids.append(entry_id)

        # 5. Regenerate hot memory so insights surface in MEMORY.md
        await self._regenerate_hot_memory(project_id)

        # Update last hash file
        try:
            hash_file_dir.mkdir(parents=True, exist_ok=True)
            hash_file_path.write_text(episodes_hash, encoding="utf-8")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning("[Dream] Failed to write last dream hash file: %s", e)

        result.finished_at = datetime.now()
        logger.info(
            "[Dream] Cycle complete: %d episodes -> %d insights (%.1fs)",
            result.episodes_replayed,
            len(result.insight_ids),
            result.duration_seconds,
        )
        return result

    async def _distill(
        self,
        episodes_text: str,
        episodes: list[dict[str, Any]],
    ) -> list[DreamInsight]:
        """Invoke LLM to extract insights from formatted episodes."""
        try:
            from app.infrastructure.llm import InternalLLMService
            from app.infrastructure.config.service import SystemConfigService

            # Build prompt via Jinja2 template
            prompt_text = render_template(
                "core/memory/dream_distillation.prompt.j2",
                episodes_text=episodes_text,
                episode_count=len(episodes),
            )

            messages = [
                {"role": "system", "content": "You are a Knowledge Architect that distills reusable insights from agent execution episodes."},
                {"role": "user", "content": prompt_text},
            ]

            model_name = SystemConfigService.get_value("LLM_MODEL")
            response = await InternalLLMService.invoke(
                messages=messages,
                purpose="memory_consolidation",
                model_name=model_name,
            )

            return self._parse_insights(response.content)

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.error("[Dream] LLM distillation failed: %s", e)
            return []

    def _parse_insights(self, content: str) -> list[DreamInsight]:
        """Parse LLM response JSON into DreamInsight objects."""
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if not match:
            logger.warning("[Dream] No JSON array found in LLM response")
            return []

        try:
            raw_insights = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            logger.warning("[Dream] Failed to parse insights JSON: %s", e)
            return []

        insights = []
        for item in raw_insights:
            try:
                insights.append(DreamInsight(
                    title=item.get("title", "")[:200],
                    content=item.get("content", "")[:2000],
                    category=item.get("category", "pattern"),
                    utility_score=float(item.get("utility_score", 0.8)),
                    related_goals=item.get("related_goals", []),
                ))
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.debug("[Dream] Skipping malformed insight: %s", e)

        return insights

    async def _store_insight(
        self,
        insight: DreamInsight,
        project_id: int | None,
    ) -> str | None:
        """Store a distilled insight as a strategic CONCEPT entry."""
        try:
            import hashlib
            content_hash = hashlib.sha256(insight.content.encode()).hexdigest()[:16]
            entry_id = f"dream_{content_hash}"

            # Dedup: skip if already exists
            existing = await self.manager.get_memory(entry_id)
            if existing:
                logger.debug("[Dream] Insight already stored: %s", entry_id)
                return None

            entry = MemoryEntry(
                id=entry_id,
                type=MemoryType.CONCEPT,
                privacy=PrivacyLevel.TEAM,
                title=insight.title,
                content=insight.content,
                description=insight.content[:200],
                project_id=project_id,
                tier=MemoryTier.STRATEGIC,
                utility_score=insight.utility_score,
                source="deep_dream",
                tags=["dream", "distilled", insight.category],
            )
            await self.manager.save_memory(entry)
            logger.info("[Dream] Stored insight: %s (%s)", entry_id, insight.category)
            return entry_id

        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.warning("[Dream] Failed to store insight: %s", e)
            return None

    async def _regenerate_hot_memory(self, project_id: int | None = None) -> None:
        """Trigger MEMORY.md regeneration so distilled insights surface in hot memory."""
        try:
            if hasattr(self.manager, "regenerate_memory_md"):
                await self.manager.regenerate_memory_md(project_id)
                logger.debug("[Dream] Hot memory regenerated")
            else:
                two_tier = getattr(self.manager, "_two_tier", None)
                if two_tier and hasattr(two_tier, "regenerate_memory_md"):
                    await two_tier.regenerate_memory_md()
                    logger.debug("[Dream] Hot memory regenerated")
        except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
            logger.debug("[Dream] Hot memory regeneration skipped: %s", e)
