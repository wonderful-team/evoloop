"""
Smart Memory Retrieval - Two-stage retrieval with LLM relevance ranking.

Inspired by Claude Code's findRelevantMemories.ts, this module implements:
1. Stage 1: Keyword-based candidate retrieval
2. Stage 2: LLM-assisted relevance selection
3. Recent tool filtering (exclude currently used tools)
4. Already-surfaced filtering (avoid repetition)

Usage:
    from app.core.memory.config import MemoryConfig
    from app.core.memory.store import MemoryStore

    config = MemoryConfig.from_settings()
    storage = MemoryStore(str(config.user_memory_root))
    retriever = MemoryRetriever(storage=storage, config=config)

    results = await retriever.find_relevant(
        query="How do I deploy this?",
        context={"recent_tools": ["docker_build", "deploy"]},
        already_surfaced={"mem_001", "mem_002"},
    )
"""

import logging
import math
import time
from datetime import datetime
from typing import Any

from app.core.memory.models import MemoryEntry, MemoryType
from app.core.memory.schemas import RetrievalContext
from app.utils.template import render_template
from app.utils.time import elapsed_ms

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """
    Two-stage memory retrieval with LLM relevance ranking.

    Stage 1: Fast keyword search to get candidates
    Stage 2: LLM selects the most relevant from candidates

    Usage:
        from app.core.memory.store import MemoryStore
        from app.core.memory.config import MemoryConfig

        config = MemoryConfig.from_settings()
        storage = MemoryStore(str(config.user_memory_root))
        retriever = MemoryRetriever(storage=storage, config=config)
    """

    def __init__(
        self,
        storage,
        config=None,
        max_candidates: int = 20,
        max_results: int = 5,
        enable_llm_selection: bool = True,
        **kwargs,
    ):
        """
        Initialize smart retriever.

        Args:
            storage: Storage backend (required)
            config: Memory configuration. Uses defaults if None.
            max_candidates: Maximum candidates for stage 1
            max_results: Maximum results to return
            enable_llm_selection: Whether to use LLM for selection
        """
        self._storage = storage
        self._config = config
        self.max_candidates = max_candidates
        self.max_results = max_results
        self.enable_llm_selection = enable_llm_selection

        # Optimization: Skip Stage 2 if Stage 1 match is high-confidence
        self.selection_skip_threshold = kwargs.get("selection_skip_threshold", 5.0)

        # Cache for LLM selection results (query_id -> selected_ids)
        self._selection_cache: dict[str, list[str]] = {}

    async def find_relevant(
        self,
        query: str,
        context: dict[str, Any] | None = None,
        already_surfaced: set[str] | None = None,
        max_results: int | None = None,
    ) -> list[MemoryEntry]:
        """
        Find relevant memories using one-stage lexical ORM search + relevance scoring.
        """
        limit = max_results if max_results is not None else self.max_results
        total_start = time.time()
        logger.info(f"[MemoryRetriever] 🔍 Lexical find_relevant for query: '{query[:50]}...'")

        ctx = RetrievalContext(
            query=query,
            recent_tools=context.get("recent_tools", []) if context else [],
            already_surfaced=already_surfaced or set(),
            member_id=context.get("member_id") if context else None,
            project_id=context.get("project_id") if context else None,
        )

        # 1. SQL LIKE 模糊匹配召回候选
        candidates = await self._storage.search(
            query=ctx.query,
            project_id=ctx.project_id,
            member_id=ctx.member_id,
            limit=self.max_candidates,
        )

        if not candidates:
            return []

        # 2. 过滤已召回过的 (already_surfaced)
        fresh_candidates = [c for c in candidates if c.id not in ctx.already_surfaced]

        if not fresh_candidates:
            return []

        # 3. 按效用（新鲜度、置信度、词频权重）本地进行一轮排序，返回 Top K
        scored = [(c, self._score_candidate(c, ctx)) for c in fresh_candidates]
        scored.sort(key=lambda x: x[1], reverse=True)

        selected = [c for c, s in scored[:limit]]
        elapsed = elapsed_ms(total_start)
        logger.info(f"[MemoryRetriever] ✓ Retrieved {len(selected)} memories in {elapsed:.1f}ms")
        return selected

    def _score_candidate(
        self,
        entry: MemoryEntry,
        ctx: RetrievalContext,
    ) -> float:
        """
        Score a candidate memory for relevance.

        Combines:
        - Keyword relevance
        - Freshness boost
        - Type priority (user/feedback higher than project/reference)
        """
        query = ctx.query.lower()
        query_words = set(query.split())

        # Keyword relevance
        text = f"{entry.title} {entry.description} {entry.content}".lower()
        keyword_score = sum(
            2 if word in entry.title.lower() else 1
            for word in query_words
            if word in text
        )

        # Freshness boost (exponential decay, 30-day half-life)
        age_days = (datetime.utcnow() - entry.updated_at).days
        freshness_boost = 1.5 * math.exp(-age_days / 30.0)

        # Type priority
        type_multiplier = {
            MemoryType.USER: 1.3,
            MemoryType.FEEDBACK: 1.2,
            MemoryType.PROJECT: 1.0,
            MemoryType.REFERENCE: 0.9,
        }.get(entry.type, 1.0)

        return (keyword_score + freshness_boost) * type_multiplier

    # ==========================================================================
    # Context Injection Methods (migrated from MemoryRetrievalService)
    # ==========================================================================

    async def get_for_context_injection(
        self,
        query: str,
        member_id: int | None = None,
        project_id: int | None = None,
    ) -> dict[str, list[MemoryEntry]]:
        """
        Get memories organized for context injection.

        Args:
            query: Current query for relevance ranking
            member_id: Member ID for private memories
            project_id: Project ID for filtering

        Returns:
            Dictionary with keys: user, feedback, project, reference
        """
        # Get all memories (filter by project early)
        all_memories = await self._storage.list_all(project_id=project_id)

        # Batch load full entries to avoid N+1
        ids = [m.id for m in all_memories]
        entry_map = await self._storage.get_multi(ids)
        entries = list(entry_map.values())

        # Filter and organize
        result = {
            "user": [],
            "feedback": [],
            "project": [],
            "reference": [],
        }

        for entry in entries:
            # Privacy check
            if entry.privacy.value == "private" and entry.member_id != member_id:
                continue

            # Project check
            if entry.project_id is not None and entry.project_id != project_id:
                continue

            # Add to appropriate bucket
            key = entry.type.value
            if key in result:
                result[key].append(entry)

        # Sort each bucket by relevance to query (simple keyword match)
        for key in result:
            result[key] = self._sort_by_relevance(result[key], query)[:3]  # Top 3 per type

        return result

    def _sort_by_relevance(
        self,
        entries: list[MemoryEntry],
        query: str,
    ) -> list[MemoryEntry]:
        """Sort entries by relevance to query (with freshness boost)."""
        query_words = set(query.lower().split())
        now = datetime.utcnow()

        def score(entry: MemoryEntry) -> float:
            # Base relevance score
            text = f"{entry.title} {entry.description} {entry.content}".lower()
            relevance = sum(1 for word in query_words if word in text)

            # Freshness boost (exponential decay, 30-day half-life)
            age_days = (now - entry.updated_at).days
            freshness_boost = 2.0 * math.exp(-age_days / 30.0)

            return relevance + freshness_boost

        return sorted(entries, key=score, reverse=True)

    async def format_for_prompt(
        self,
        memories: dict[str, list[MemoryEntry]],
    ) -> str:
        """
        Format memories for injection into system prompt.

        Args:
            memories: Dictionary of memories by type

        Returns:
            Formatted string for prompt
        """
        return render_template(
            "core/memory/context_injection.prompt.j2",
            user_memories=memories.get("user", []),
            feedback_memories=memories.get("feedback", []),
            project_memories=memories.get("project", []),
            reference_memories=memories.get("reference", []),
        )


async def _get_global_memory_container() -> Any:
    """Get global memory container via MemoryLifespanManager (singleton)."""
    from app.core.memory.lifespan import MemoryLifespanManager

    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()

    return MemoryLifespanManager.get_container()


async def get_relevant_memories(
    query: str,
    member_id: int | None = None,
    project_id: int | None = None,
    max_results: int = 5,
    already_surfaced: set[str] | None = None,
    context: dict[str, Any] | None = None,
) -> list[MemoryEntry]:
    """
    Convenience function to get relevant memories using smart retrieval.

    Uses a global singleton container to avoid repeated initialization overhead.

    Args:
        query: The search query
        member_id: Optional user member ID for filtering
        project_id: Optional project ID for filtering
        max_results: Maximum number of results to return
        already_surfaced: Set of memory IDs already shown to user (to avoid repetition)
        context: Optional context dict with keys like "recent_tools"

    Returns:
        List of relevant memory entries
    """
    container = await _get_global_memory_container()

    # Reuse the singleton retriever from the container so that
    # _selection_cache is actually shared across calls.
    retriever = container.retrieval_service
    retriever.max_results = max_results

    ctx = context or {}
    ctx.update({
        "member_id": member_id,
        "project_id": project_id,
    })

    return await retriever.find_relevant(query, ctx, already_surfaced)
