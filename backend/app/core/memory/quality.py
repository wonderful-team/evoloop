"""
Memory Quality Scoring and Maintenance

This module provides:
1. Quality scoring for memories (freshness, usage, specificity, actionability)
2. Stale memory detection
3. Cleanup recommendations
4. Automatic quality improvement suggestions

Inspired by Claude Code's memory management and drift detection.
"""

import logging
import math
import re
from collections import defaultdict
from datetime import datetime

from pydantic import Field

from app.core.memory.constants import FRESHNESS_HALF_LIFE
from app.core.memory.models import MemoryEntry
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class QualityScores(DynamicBaseModel):
    """Heuristic quality scores for a memory entry (metadata-based)."""

    freshness: float  # 0-1, how recent
    usage: float  # 0-1, how often recalled
    specificity: float  # 0-1, how specific (vs vague)
    actionability: float  # 0-1, how actionable
    overall: float  # Weighted average


class CleanupRecommendation(DynamicBaseModel):
    """Recommendation for memory cleanup."""

    entry: MemoryEntry
    action: str  # 'archive', 'update', 'delete', 'keep'
    reason: str
    scores: QualityScores
    suggestions: list[str] = Field(default_factory=list)


class MemoryQualityAnalyzer:
    """
    Analyze memory quality and provide maintenance recommendations.

    Usage:
        from app.core.memory.config import MemoryConfig
        from app.core.memory.store import MemoryStore

        config = MemoryConfig.from_settings()
        storage = MemoryStore(str(config.user_memory_root))
        analyzer = MemoryQualityAnalyzer(storage=storage, config=config)
    """

    # Quality thresholds

    # Weights for overall score
    WEIGHTS = {
        "freshness": 0.25,
        "usage": 0.30,
        "specificity": 0.25,
        "actionability": 0.20,
    }

    def __init__(
        self,
        storage,
        config=None,
    ):
        """
        Initialize quality analyzer.

        Args:
            storage: Storage backend (required)
            config: Memory configuration. Uses defaults if None.
        """
        self._storage = storage
        self._config = config
        self._access_counts: dict[str, int] = defaultdict(int)

    async def analyze_memory(self, entry: MemoryEntry) -> QualityScores:
        """
        Calculate quality scores for a memory entry.

        Returns scores for:
        - Freshness: How recent (exponential decay)
        - Usage: How often recalled
        - Specificity: How specific vs vague
        - Actionability: How actionable the content is
        """
        freshness = self._score_freshness(entry)
        usage = await self._score_usage(entry)
        specificity = self._score_heuristic_specificity(entry)
        actionability = self._score_heuristic_actionability(entry)

        # Weighted overall score
        overall = (
            freshness * self.WEIGHTS["freshness"]
            + usage * self.WEIGHTS["usage"]
            + specificity * self.WEIGHTS["specificity"]
            + actionability * self.WEIGHTS["actionability"]
        )

        return QualityScores(
            freshness=freshness,
            usage=usage,
            specificity=specificity,
            actionability=actionability,
            overall=overall,
        )

    def _score_freshness(self, entry: MemoryEntry) -> float:
        """
        Score memory freshness (0-1).

        Uses exponential decay with 30-day half-life.
        """
        age_days = (datetime.utcnow() - entry.updated_at).days
        return math.exp(-age_days / FRESHNESS_HALF_LIFE)

    async def _score_usage(self, entry: MemoryEntry) -> float:
        """
        Score memory usage/recall frequency (0-1).

        Based on how often the memory has been recalled.
        For now, uses a simple access count.
        """
        access_count = self._access_counts.get(entry.id, 0)

        # Normalize: 0 accesses = 0, 10+ accesses = 1
        return min(1.0, access_count / 10.0)

    def _score_heuristic_specificity(self, entry: MemoryEntry) -> float:
        """
        Score how specific the memory is (0-1).

        Vague memories are less useful. Look for:
        - Concrete nouns (files, functions, tools)
        - Specific numbers/dates
        - Named entities
        """
        content = entry.content.lower()

        # Positive indicators (specific)
        specific_patterns = [
            r"\b\w+\.(py|js|ts|java|go|rs|cpp|c|h)\b",  # File extensions
            r"\b[A-Z][a-z]+[A-Z]\w*\b",  # CamelCase (likely class names)
            r"\b\d{4}-\d{2}-\d{2}\b",  # Dates
            r"\b(v\d+\.\d+|version \d+)\b",  # Versions
            r"`[^`]+`",  # Code/inline references
        ]

        specific_score = sum(
            1 for pattern in specific_patterns if re.search(pattern, content)
        ) / len(specific_patterns)

        # Negative indicators (vague)
        vague_words = ["something", "somehow", "maybe", "probably", "thing", "stuff"]
        vague_count = sum(1 for word in vague_words if word in content)
        vague_penalty = min(0.5, vague_count * 0.1)

        return max(0.0, min(1.0, specific_score - vague_penalty))

    def _score_heuristic_actionability(self, entry: MemoryEntry) -> float:
        """
        Score how actionable the memory is (0-1).

        Actionable memories include:
        - Direct instructions ("Use X", "Don't do Y")
        - Conditional guidance ("When X, do Y")
        - Specific constraints
        """
        content = entry.content.lower()

        # Actionable patterns
        actionable_patterns = [
            r"\b(use|avoid|prefer|always|never|don\'t|should|must)\b",
            r"\b(when|if)\s+\w+[,\s]+(then|do|use)\b",
            r"\b(step \d+|first|second|third|finally)\b",
            r"\b(why:|how to apply:|context:)\b",
        ]

        action_score = sum(
            1 for pattern in actionable_patterns if re.search(pattern, content)
        ) / len(actionable_patterns)

        # Boost for structured memories (have Why/How sections)
        if "**why:**" in content or "**how to apply:**" in content:
            action_score += 0.3

        return min(1.0, action_score)

    async def get_cleanup_recommendations(
        self,
        project_id: int | None = None,
        min_quality: float = 0.3,
    ) -> list[CleanupRecommendation]:
        """
        Get recommendations for memory cleanup.

        Returns memories that should be archived, updated, or deleted.
        """
        # Get all memories (lightweight summaries)
        memories = await self._storage.list_all(project_id=project_id)

        # Batch load full entries to avoid N+1 queries
        ids = [m.id for m in memories]
        entry_map = await self._storage.get_multi(ids)

        recommendations = []

        for _mem_id, entry in entry_map.items():
            # Filter by project (though already filtered in list_all, double check)
            if project_id is not None and entry.project_id != project_id:
                continue

            scores = await self.analyze_memory(entry)

            if scores.overall < min_quality:
                action, reason, suggestions = self._determine_action(entry, scores)

                recommendations.append(
                    CleanupRecommendation(
                        entry=entry,
                        action=action,
                        reason=reason,
                        scores=scores,
                        suggestions=suggestions,
                    )
                )

        # Sort by overall score (lowest first)
        recommendations.sort(key=lambda r: r.scores.overall)

        return recommendations

    def _determine_action(
        self,
        entry: MemoryEntry,
        scores: QualityScores,
    ) -> tuple[str, str, list[str]]:
        """
        Determine what action to take for a low-quality memory.

        Returns: (action, reason, suggestions)
        """
        suggestions = []

        # Check freshness
        if scores.freshness < 0.3:
            age_days = (datetime.utcnow() - entry.updated_at).days

            # Very old project memories might be outdated
            if entry.type.value == "project" and age_days > 90:
                return (
                    "archive",
                    f"Very old project memory ({age_days} days). Likely outdated.",
                    [
                        "Verify if still relevant",
                        "Update with current state",
                        "Archive if obsolete",
                    ],
                )

            suggestions.append("Update with more recent information")

        # Check specificity
        if scores.specificity < 0.3:
            suggestions.append("Add specific file names, functions, or tools")
            suggestions.append("Include concrete examples")

        # Check actionability
        if scores.actionability < 0.3:
            suggestions.append("Add specific guidance on when/how to apply")
            suggestions.append("Include 'Why' and 'How to apply' sections")

        # Check usage
        if scores.usage < 0.1:
            suggestions.append("Consider if this memory is actually useful")

        # Determine overall action
        if scores.overall < 0.2:
            return "delete", "Very low quality, unlikely to be useful", suggestions
        elif scores.freshness < 0.2:
            return "update", "Outdated but potentially valuable", suggestions
        else:
            return "improve", "Could be improved", suggestions

    def get_access_count(self, entry_id: str) -> int:
        """Get the number of times a memory was accessed (public API)."""
        return self._access_counts.get(entry_id, 0)
