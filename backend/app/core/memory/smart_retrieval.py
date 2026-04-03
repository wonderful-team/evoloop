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
    retriever = SmartMemoryRetriever(storage=storage, config=config)
    
    results = await retriever.find_relevant(
        query="How do I deploy this?",
        context={"recent_tools": ["docker_build", "deploy"]},
        already_surfaced={"mem_001", "mem_002"},
    )
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any, Set
import json
import math

from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
from app.utils.template import render_template

logger = logging.getLogger(__name__)


@dataclass
class RetrievalContext:
    """Context for memory retrieval."""
    query: str
    recent_tools: List[str]
    already_surfaced: Set[str]  # Memory IDs already shown to user
    user_id: Optional[str] = None
    project_id: Optional[int] = None


class SmartMemoryRetriever:
    """
    Two-stage memory retrieval with LLM relevance ranking.
    
    Stage 1: Fast keyword search to get candidates
    Stage 2: LLM selects the most relevant from candidates
    
    Usage:
        from app.core.memory.config import MemoryConfig
        from app.core.memory.backends.file_backend import FileMemoryStorage
        
        config = MemoryConfig.from_settings()
        storage = FileMemoryStorage(str(config.memory_root))
        retriever = SmartMemoryRetriever(storage=storage, config=config)
    """
    
    def __init__(
        self,
        storage,
        config=None,
        max_candidates: int = 20,
        max_results: int = 5,
        enable_llm_selection: bool = True,
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
    
    async def find_relevant(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        already_surfaced: Optional[Set[str]] = None,
    ) -> List[MemoryEntry]:
        """
        Find relevant memories using two-stage retrieval.
        
        Args:
            query: User query
            context: Additional context including recent_tools
            already_surfaced: Set of memory IDs already shown
            
        Returns:
            List of relevant memory entries
        """
        ctx = RetrievalContext(
            query=query,
            recent_tools=context.get("recent_tools", []) if context else [],
            already_surfaced=already_surfaced or set(),
            user_id=context.get("user_id") if context else None,
            project_id=context.get("project_id") if context else None,
        )
        
        # Stage 1: Get candidates
        candidates = await self._get_candidates(ctx)
        
        if not candidates:
            logger.debug(f"[SmartRetrieval] No candidates found for query: {query[:50]}")
            return []
        
        # Filter out already surfaced
        fresh_candidates = [
            c for c in candidates 
            if c.id not in ctx.already_surfaced
        ]
        
        if not fresh_candidates:
            logger.debug(f"[SmartRetrieval] All candidates already surfaced")
            return []
        
        # If few enough, return all
        if len(fresh_candidates) <= self.max_results:
            return fresh_candidates
        
        # Stage 2: LLM selection (if enabled)
        if self.enable_llm_selection:
            selected = await self._llm_select(fresh_candidates, ctx)
        else:
            # Fallback: keyword ranking with freshness
            selected = self._keyword_rank(fresh_candidates, ctx)[:self.max_results]
        
        logger.info(
            f"[SmartRetrieval] Query: '{query[:40]}...' | "
            f"Candidates: {len(candidates)} | "
            f"Selected: {len(selected)}"
        )
        
        return selected
    
    async def _get_candidates(
        self,
        ctx: RetrievalContext,
    ) -> List[MemoryEntry]:
        """
        Stage 1: Get candidate memories using keyword search.
        
        Strategy:
        1. Search all accessible memories
        2. Filter by privacy and project
        3. Score by keyword match + freshness
        4. Return top N candidates
        """
        # Get all memories
        all_memories = await self._storage.list_all()
        
        # Load full entries and filter
        candidates = []
        for mem_summary in all_memories:
            # Skip if already surfaced
            if mem_summary.id in ctx.already_surfaced:
                continue
            
            # Load full entry
            entry = await self._storage.get(mem_summary.id)
            if not entry:
                continue
            
            # Privacy filter
            if entry.privacy == PrivacyLevel.PRIVATE and entry.user_id != ctx.user_id:
                continue
            
            # Project filter
            if entry.project_id is not None and entry.project_id != ctx.project_id:
                continue
            
            candidates.append(entry)
        
        # Score and rank
        scored = [(c, self._score_candidate(c, ctx)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Return top candidates
        return [entry for entry, score in scored[:self.max_candidates]]
    
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
        candidates: List[MemoryEntry],
        ctx: RetrievalContext,
    ) -> List[MemoryEntry]:
        """
        Stage 2: Use LLM to select most relevant memories.
        
        This is more accurate than keyword matching because:
        - LLM understands semantic similarity
        - Can judge which memories are truly useful
        - Can filter out misleading keyword matches
        """
        from app.infrastructure.llm.factory import get_default_llm
        
        try:
            # Build selection prompt
            prompt = self._build_selection_prompt(candidates, ctx)
            
            # Call LLM (get_default_llm returns a Task in async context)
            llm_result = get_default_llm(temperature=0.3, max_tokens=500)
            llm = await llm_result if hasattr(llm_result, '__await__') else llm_result
            response = await llm.ainvoke([
                {"role": "system", "content": "You are a memory relevance selector."},
                {"role": "user", "content": prompt},
            ])
            
            # Parse selection
            selected_ids = self._parse_selection_response(
                response.content if hasattr(response, 'content') else str(response),
                candidates,
            )
            
            # Return selected entries
            id_to_entry = {e.id: e for e in candidates}
            return [id_to_entry[mid] for mid in selected_ids if mid in id_to_entry]
            
        except Exception as e:
            logger.error(f"[SmartRetrieval] LLM selection failed: {e}")
            # Fallback to keyword ranking
            return self._keyword_rank(candidates, ctx)[:self.max_results]
    
    def _build_selection_prompt(
        self,
        candidates: List[MemoryEntry],
        ctx: RetrievalContext,
    ) -> str:
        """Build the LLM selection prompt."""
        # Filter out recently used tools from candidates
        filtered_candidates = self._filter_recent_tools(candidates, ctx.recent_tools)
        
        # Build memory list
        memory_list = []
        for i, mem in enumerate(filtered_candidates, 1):
            memory_list.append(
                f"{i}. [{mem.type.value}] {mem.title}\n"
                f"   {mem.description[:100]}"
            )
        
        recent_tools_section = ""
        if ctx.recent_tools:
            recent_tools_section = f"\nRecently used tools: {', '.join(ctx.recent_tools)}\nDo NOT select memories about these tools (already in use)."
        
        return f"""You are selecting memories that will be useful to process this query.

Query: "{ctx.query}"

Available memories:
{chr(10).join(memory_list)}
{recent_tools_section}

Instructions:
- Select up to {self.max_results} memories that are MOST relevant to the query
- Focus on memories that provide actionable guidance
- Skip memories that are only vaguely related
- Prefer recent memories over old ones
- Do not select memories about tools listed in "Recently used tools"

Return your selection as JSON:
```json
{{
  "selected_indices": [1, 3, 5],
  "reasoning": "Brief explanation of why these were selected"
}}
```

If no memories are relevant, return: {{"selected_indices": []}}"""
    
    def _filter_recent_tools(
        self,
        candidates: List[MemoryEntry],
        recent_tools: List[str],
    ) -> List[MemoryEntry]:
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
        candidates: List[MemoryEntry],
    ) -> List[str]:
        """Parse LLM selection response."""
        import re
        
        try:
            # Extract JSON block
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # Try parsing entire response
                data = json.loads(response)
            
            indices = data.get("selected_indices", [])
            
            # Convert 1-based indices to IDs
            selected_ids = []
            for idx in indices:
                if 1 <= idx <= len(candidates):
                    selected_ids.append(candidates[idx - 1].id)
            
            return selected_ids[:self.max_results]
            
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"[SmartRetrieval] Failed to parse selection: {e}")
            # Fallback: return first N
            return [c.id for c in candidates[:self.max_results]]
    
    def _keyword_rank(
        self,
        candidates: List[MemoryEntry],
        ctx: RetrievalContext,
    ) -> List[MemoryEntry]:
        """Fallback: Rank candidates by keyword relevance."""
        scored = [(c, self._score_candidate(c, ctx)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [entry for entry, score in scored]


async def get_relevant_memories(
    query: str,
    user_id: Optional[str] = None,
    project_id: Optional[int] = None,
    max_results: int = 5,
    already_surfaced: Optional[Set[str]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> List[MemoryEntry]:
    """
    Convenience function to get relevant memories using smart retrieval.
    
    This function creates a temporary SmartMemoryRetriever with the
    default storage backend.
    
    Args:
        query: The search query
        user_id: Optional user ID for filtering
        project_id: Optional project ID for filtering
        max_results: Maximum number of results to return
        already_surfaced: Set of memory IDs already shown to user (to avoid repetition)
        context: Optional context dict with keys like "recent_tools"
        
    Returns:
        List of relevant memory entries
        
    Example:
        entries = await get_relevant_memories(
            query="How do I deploy?",
            user_id="user_123",
            project_id=456,
            already_surfaced={"mem_001", "mem_002"},
        )
    """
    from app.core.memory import MemoryContainer, MemoryConfig
    
    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    
    try:
        retriever = SmartMemoryRetriever(
            storage=container.storage,
            config=container.config,
            max_results=max_results,
        )
        
        ctx = context or {}
        ctx.update({
            "user_id": user_id,
            "project_id": project_id,
        })
        
        return await retriever.find_relevant(query, ctx, already_surfaced)
    finally:
        await container.shutdown()
