"""
Smart Memory Retrieval - Two-stage retrieval with LLM relevance ranking.

Inspired by Claude Code's findRelevantMemories.ts, this module implements:
1. Stage 1: Keyword-based candidate retrieval
2. Stage 2: LLM-assisted relevance selection
3. Recent tool filtering (exclude currently used tools)
4. Already-surfaced filtering (avoid repetition)

Usage:
    from app.core.memory.config import MemoryConfig
    from app.core.memory.backends.file_backend import FileMemoryStorage
    
    config = MemoryConfig.from_settings()
    storage = FileMemoryStorage(str(config.memory_root))
    retriever = MemoryRetriever(storage=storage, config=config)
    
    results = await retriever.find_relevant(
        query="How do I deploy this?",
        context={"recent_tools": ["docker_build", "deploy"]},
        already_surfaced={"mem_001", "mem_002"},
    )
"""

import json
import logging
import math
import time
from datetime import datetime
from typing import Any

from app.core.memory.models import MemoryEntry, MemoryType
from app.core.memory.schemas import RetrievalContext
from app.utils.template import render_template

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """
    Two-stage memory retrieval with LLM relevance ranking.
    
    Stage 1: Fast keyword search to get candidates
    Stage 2: LLM selects the most relevant from candidates
    
    Usage:
        from app.core.memory.config import MemoryConfig
        from app.core.memory.backends.file_backend import FileMemoryStorage
        
        config = MemoryConfig.from_settings()
        storage = FileMemoryStorage(str(config.memory_root))
        retriever = MemoryRetriever(storage=storage, config=config)
    """

    def __init__(
        self,
        storage,
        config=None,
        max_candidates: int = 20,
        max_results: int = 5,
        enable_llm_selection: bool = True,
        **kwargs
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
        Find relevant memories using two-stage retrieval.

        Args:
            query: User query
            context: Additional context including recent_tools
            already_surfaced: Set of memory IDs already shown
            max_results: Override the instance's max_results for this call

        Returns:
            List of relevant memory entries
        """
        # Allow per-call override of max_results while preserving the instance default
        limit = max_results if max_results is not None else self.max_results
        total_start = time.time()
        logger.info(f"[MemoryRetriever] 🔍 Starting find_relevant for query: '{query[:50]}...'")

        ctx = RetrievalContext(
            query=query,
            recent_tools=context.get("recent_tools", []) if context else [],
            already_surfaced=already_surfaced or set(),
            user_id=context.get("user_id") if context else None,
            project_id=context.get("project_id") if context else None,
        )
        logger.debug(f"[MemoryRetriever] Context: user_id={ctx.user_id}, project_id={ctx.project_id}, already_surfaced={len(ctx.already_surfaced)}")

        # Stage 1: Get candidates
        stage1_start = time.time()
        candidates = await self._get_candidates(ctx)
        stage1_elapsed = (time.time() - stage1_start) * 1000
        logger.info(f"[MemoryRetriever] 📊 Stage 1 (_get_candidates): {len(candidates)} candidates in {stage1_elapsed:.1f}ms")

        if not candidates:
            logger.warning(f"[MemoryRetriever] ❌ No candidates found for query: {query[:50]}")
            return []

        # Filter out already surfaced
        filter_start = time.time()
        fresh_candidates = [
            c for c in candidates
            if c.id not in ctx.already_surfaced
        ]
        filter_elapsed = (time.time() - filter_start) * 1000
        filtered_count = len(candidates) - len(fresh_candidates)
        logger.info(f"[MemoryRetriever] 🔄 Filtering already_surfaced: {filtered_count} removed, {len(fresh_candidates)} remaining in {filter_elapsed:.1f}ms")

        if not fresh_candidates:
            logger.warning("[MemoryRetriever] ❌ All candidates already surfaced")
            return []

        # Optimization: Check if keyword match is high enough to skip Stage 2
        # Use the highest score from scored candidates (which were sorted)
        # We need to get the scores from Stage 1
        scored_candidates = [(c, self._score_candidate(c, ctx)) for c in fresh_candidates]
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        max_score = scored_candidates[0][1] if scored_candidates else 0

        if max_score >= self.selection_skip_threshold:
            selected = [c for c, s in scored_candidates[:limit]]
            total_elapsed = (time.time() - total_start) * 1000
            logger.info(
                f"[MemoryRetriever] 🚀 Skipping Stage 2 (LLM): High confidence keyword match "
                f"({max_score:.1f} >= {self.selection_skip_threshold}) in {total_elapsed:.1f}ms"
            )
            return selected

        # If few enough, return all
        if len(fresh_candidates) <= limit:
            total_elapsed = (time.time() - total_start) * 1000
            logger.info(f"[MemoryRetriever] ✓ Returning all {len(fresh_candidates)} candidates (<= max_results={limit}) in {total_elapsed:.1f}ms")
            return fresh_candidates

        # Stage 2: LLM selection (if enabled)
        logger.info(f"[MemoryRetriever] 🧠 Stage 2: Selection mode={'LLM' if self.enable_llm_selection else 'Keyword'}, fresh_candidates={len(fresh_candidates)}, max_results={limit}")

        if self.enable_llm_selection:
            # Check cache
            cache_key = f"{ctx.query}:{len(fresh_candidates)}:{[c.id for c in fresh_candidates[:10]]}"
            if cache_key in self._selection_cache:
                selected_ids = self._selection_cache[cache_key]
                id_to_entry = {e.id: e for e in fresh_candidates}
                selected = [id_to_entry[mid] for mid in selected_ids if mid in id_to_entry]
                logger.info(f"[MemoryRetriever] ⚡ Cache HIT for LLM selection: {len(selected)} items")
                return selected

            stage2_start = time.time()
            selected = await self._llm_select(fresh_candidates, ctx)
            stage2_elapsed = (time.time() - stage2_start) * 1000

            # Save to cache
            self._selection_cache[cache_key] = [c.id for c in selected]
            logger.info(f"[MemoryRetriever] 🧠 Stage 2 (_llm_select): {len(selected)} selected in {stage2_elapsed:.1f}ms")
        else:
            stage2_start = time.time()
            selected = self._keyword_rank(fresh_candidates, ctx)[:limit]
            stage2_elapsed = (time.time() - stage2_start) * 1000
            logger.info(f"[MemoryRetriever] 📈 Stage 2 (_keyword_rank): {len(selected)} selected in {stage2_elapsed:.1f}ms")

        total_elapsed = (time.time() - total_start) * 1000
        logger.info(
            f"[MemoryRetriever] ✅ COMPLETED: '{query[:40]}...' | "
            f"Candidates: {len(candidates)} | "
            f"Selected: {len(selected)} | "
            f"Total: {total_elapsed:.1f}ms"
        )

        return selected

    async def _get_candidates(self, ctx: RetrievalContext) -> list[MemoryEntry]:
        """
        Stage 1: Get candidate memories using high-performance storage search.

        Now uses the storage backend's search() method which is backed by 
        SQLite indices and Vector search (LanceDB).
        """
        start_time = time.time()
        logger.debug(f"[_get_candidates] Querying storage with query='{ctx.query[:50]}'")

        # 1. High-performance search from storage backend
        # Note: We request more than max_candidates to allow for local Stage 1 scoring/filtering
        candidates = await self._storage.search(
            query=ctx.query,
            project_id=ctx.project_id,
            limit=self.max_candidates * 2
        )

        # 2. Local Stage 1 Scoring (Combines vector similarity with freshness/type priority)
        # storage.search already returns hydrated MemoryEntry objects
        scored = [(c, self._score_candidate(c, ctx)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # 3. Return top candidates
        result = [entry for entry, score in scored[:self.max_candidates]]
        
        elapsed = (time.time() - start_time) * 1000
        logger.debug(f"[_get_candidates] Found {len(candidates)} candidates, ranked top {len(result)} in {elapsed:.1f}ms")

        return result

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
        keyword_score = sum(2 if word in entry.title.lower() else 1
                          for word in query_words
                          if word in text)

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

    async def _llm_select(
        self,
        candidates: list[MemoryEntry],
        ctx: RetrievalContext,
    ) -> list[MemoryEntry]:
        """
        Stage 2: Use LLM to select most relevant memories.

        This is more accurate than keyword matching because:
        - LLM understands semantic similarity
        - Can judge which memories are truly useful
        - Can filter out misleading keyword matches

        Note: This is an internal operation - callbacks are disabled to prevent
        internal selection JSON from appearing in the user-facing chat.
        """
        from app.core.llm import InternalLLMService

        total_start = time.time()
        logger.info(f"[_llm_select] Starting LLM selection for {len(candidates)} candidates")

        try:
            # Build selection prompt using standardized builder
            from app.core.memory.prompts import MemoryRetrievalPromptBuilder

            # Prepare candidates for template
            candidates_for_llm = []
            filtered_candidates = self._filter_recent_tools(candidates, ctx.recent_tools)
            
            for mem in filtered_candidates:
                candidates_for_llm.append({
                    "title": mem.title,
                    "type": mem.type.value,
                    "description": mem.description,
                    "updated_at": mem.updated_at.isoformat() if mem.updated_at else "Unknown"
                })

            builder = MemoryRetrievalPromptBuilder(
                query=ctx.query,
                memories=candidates_for_llm,
                recent_tools=ctx.recent_tools,
                max_selections=self._config.max_selections if self._config else 5
            )

            selection_messages = await builder.build()

            # Call LLM using InternalLLMService (automatically disables callbacks)
            llm_start = time.time()
            logger.info("[_llm_select] Calling InternalLLMService.invoke for memory_selection...")

            from app.infrastructure.config.service import SystemConfigService
            model_name = SystemConfigService.get_value("LLM_MODEL")
            response = await InternalLLMService.invoke(
                messages=selection_messages,
                purpose="memory_selection",
                temperature=0.3,
                max_tokens=500,
                model_name=model_name,
            )

            llm_elapsed = (time.time() - llm_start) * 1000
            logger.info(f"[_llm_select] LLM invocation completed in {llm_elapsed:.1f}ms")

            # Parse selection
            parse_start = time.time()
            content = response.content
            content_preview = content if content else "(empty)"
            logger.debug(f"[_llm_select] Response content preview: {content_preview}...")

            selected_ids = self._parse_selection_response(content, candidates)
            parse_elapsed = (time.time() - parse_start) * 1000
            logger.info(f"[_llm_select] Parsed selection: {len(selected_ids)} IDs in {parse_elapsed:.1f}ms, IDs={selected_ids}")

            # Return selected entries
            id_to_entry = {e.id: e for e in candidates}
            result = [id_to_entry[mid] for mid in selected_ids if mid in id_to_entry]

            total_elapsed = (time.time() - total_start) * 1000
            logger.info(f"[_llm_select] COMPLETED: {len(result)} entries selected in {total_elapsed:.1f}ms (LLM: {llm_elapsed:.1f}ms)")

            return result

        except Exception as e:
            total_elapsed = (time.time() - total_start) * 1000
            logger.error(f"[_llm_select] FAILED after {total_elapsed:.1f}ms: {e}")
            # Fallback to keyword ranking
            fallback_start = time.time()
            fallback_result = self._keyword_rank(candidates, ctx)[:self.max_results]
            fallback_elapsed = (time.time() - fallback_start) * 1000
            logger.warning(f"[_llm_select] Fallback to keyword_rank took {fallback_elapsed:.1f}ms, returning {len(fallback_result)} entries")
            return fallback_result

    def _filter_recent_tools(
        self,
        candidates: list[MemoryEntry],
        recent_tools: list[str],
    ) -> list[MemoryEntry]:
        """
        Filter out memories about recently used tools.
        
        Rationale: If the user is actively using a tool, showing documentation
        about that tool is noise. But we still want warnings/gotchas.
        """
        if not recent_tools:
            return candidates

        filtered = []
        tool_names = [t.lower() for t in recent_tools]

        for mem in candidates:
            mem_text = f"{mem.title} {mem.description} {mem.content}".lower()

            # Check if memory is about a recent tool
            is_about_recent_tool = any(
                tool in mem_text
                for tool in tool_names
            )

            # Check if it contains warnings/gotchas (still useful)
            has_warnings = any(
                kw in mem_text
                for kw in ["warning", "caution", "gotcha", "important", "don't"]
            )

            # Keep if not about recent tool, or if it has warnings
            if not is_about_recent_tool or has_warnings:
                filtered.append(mem)

        return filtered

    def _parse_selection_response(
        self,
        response: str,
        candidates: list[MemoryEntry],
    ) -> list[str]:
        """Parse LLM selection response."""
        import re
        start_time = time.time()

        try:
            # Extract JSON block
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                logger.debug("[_parse_selection_response] Extracted JSON from code block")
            else:
                # Try parsing entire response
                data = json.loads(response)
                logger.debug("[_parse_selection_response] Parsed entire response as JSON")

            indices = data.get("selected_indices", [])
            reasoning = data.get("reasoning", "")

            # Convert 1-based indices to IDs
            selected_ids = []
            for idx in indices:
                if 1 <= idx <= len(candidates):
                    selected_ids.append(candidates[idx - 1].id)
                else:
                    logger.warning(f"[_parse_selection_response] Index {idx} out of range (1-{len(candidates)})")

            elapsed = (time.time() - start_time) * 1000
            logger.info(f"[_parse_selection_response] Parsed {len(selected_ids)} IDs from {len(indices)} indices in {elapsed:.1f}ms")
            if reasoning:
                logger.debug(f"[_parse_selection_response] Reasoning: {reasoning[:100]}...")

            return selected_ids[:self.max_results]

        except (json.JSONDecodeError, AttributeError) as e:
            elapsed = (time.time() - start_time) * 1000
            logger.warning(f"[_parse_selection_response] Failed to parse after {elapsed:.1f}ms: {e}")
            # Fallback: return first N
            fallback_ids = [c.id for c in candidates[:self.max_results]]
            logger.warning(f"[_parse_selection_response] Fallback: returning first {len(fallback_ids)} IDs")
            return fallback_ids

    def _keyword_rank(
        self,
        candidates: list[MemoryEntry],
        ctx: RetrievalContext,
    ) -> list[MemoryEntry]:
        """Fallback: Rank candidates by keyword relevance."""
        scored = [(c, self._score_candidate(c, ctx)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [entry for entry, score in scored]

    # ==========================================================================
    # Context Injection Methods (migrated from MemoryRetrievalService)
    # ==========================================================================

    async def get_for_context_injection(
        self,
        query: str,
        user_id: str | None = None,
        project_id: int | None = None,
    ) -> dict[str, list[MemoryEntry]]:
        """
        Get memories organized for context injection.
        
        Args:
            query: Current query for relevance ranking
            user_id: User ID for private memories
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
            if entry.privacy.value == "private" and entry.user_id != user_id:
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
    user_id: str | None = None,
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
        user_id: Optional user ID for filtering
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
        "user_id": user_id,
        "project_id": project_id,
    })

    return await retriever.find_relevant(query, ctx, already_surfaced)
