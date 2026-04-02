"""
Memory Retrieval Service

Smart memory retrieval using LLM-assisted relevance selection.
Inspired by Claude Code's findRelevantMemories.
"""

import logging
from typing import List, Optional, Dict, Any

from app.core.memory.models import MemoryEntry, MemoryType
from app.core.memory.backends.file_backend import FileMemoryStorage
from app.utils.template import render_template

logger = logging.getLogger(__name__)


class MemoryRetrievalService:
    """
    Service for intelligent memory retrieval.
    
    Unlike simple keyword search, this service uses LLM to select
    the most relevant memories based on semantic understanding.
    """
    
    def __init__(self, storage: FileMemoryStorage):
        """
        Initialize retrieval service.
        
        Args:
            storage: Memory storage backend
        """
        self.storage = storage
    
    async def find_relevant(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        max_results: int = 5,
    ) -> List[MemoryEntry]:
        """
        Find memories relevant to the current query.
        
        Uses a two-stage process:
        1. Retrieve candidate memories (keyword search)
        2. Use LLM to select the most relevant ones
        
        Args:
            query: User query
            context: Additional context (recent tools, etc.)
            max_results: Maximum number of results
            
        Returns:
            List of relevant memory entries
        """
        # Stage 1: Get candidates
        candidates = await self._get_candidates(query, limit=20)
        
        if not candidates:
            return []
        
        if len(candidates) <= max_results:
            # Few enough to return all
            return [await self.storage.get(c.id) for c in candidates if c.id]
        
        # Stage 2: LLM selection
        selected_ids = await self._llm_select_memories(
            query=query,
            candidates=candidates,
            recent_tools=context.get("recent_tools", []) if context else [],
            max_selections=max_results,
        )
        
        # Load full entries for selected IDs
        results = []
        for mem_id in selected_ids:
            entry = await self.storage.get(mem_id)
            if entry:
                results.append(entry)
        
        return results
    
    async def _get_candidates(
        self,
        query: str,
        limit: int = 20,
    ) -> List[Any]:
        """
        Get candidate memories using keyword search.
        
        Args:
            query: Search query
            limit: Maximum candidates
            
        Returns:
            List of memory search results
        """
        # Simple keyword search for candidates
        return await self.storage.list_all()
    
    async def _llm_select_memories(
        self,
        query: str,
        candidates: List[Any],
        recent_tools: List[str],
        max_selections: int,
    ) -> List[str]:
        """
        Use LLM to select most relevant memories.
        
        Args:
            query: User query
            candidates: Candidate memories
            recent_tools: Recently used tools
            max_selections: Maximum to select
            
        Returns:
            List of selected memory IDs
        """
        from app.infrastructure.llm.factory import get_default_llm
        import json
        
        try:
            # Build selection prompt
            prompt = render_template(
                "memory/retrieval_selection.prompt.j2",
                query=query,
                memories=[{
                    "title": m.title,
                    "type": m.type.value if hasattr(m, 'type') else 'unknown',
                    "description": m.description,
                    "updated_at": m.updated_at.isoformat() if hasattr(m, 'updated_at') else '',
                } for m in candidates],
                recent_tools=recent_tools,
                max_selections=max_selections,
            )
            
            # Call LLM
            llm = get_default_llm(temperature=0.3)
            response = await llm.ainvoke([
                {"role": "system", "content": "You are a memory relevance selector."},
                {"role": "user", "content": prompt},
            ])
            
            # Parse response
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Extract JSON
            try:
                data = json.loads(content)
                indices = data.get("selected_indices", [])
                
                # Convert 1-based indices to IDs
                selected_ids = []
                for idx in indices:
                    if 1 <= idx <= len(candidates):
                        selected_ids.append(candidates[idx - 1].id)
                
                return selected_ids
                
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse LLM selection response: {content}")
                # Fallback: return first N candidates
                return [c.id for c in candidates[:max_selections]]
                
        except Exception as e:
            logger.error(f"LLM memory selection failed: {e}")
            # Fallback: return first N candidates
            return [c.id for c in candidates[:max_selections]]
    
    async def get_for_context_injection(
        self,
        query: str,
        user_id: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> Dict[str, List[MemoryEntry]]:
        """
        Get memories organized for context injection.
        
        Args:
            query: Current query for relevance ranking
            user_id: User ID for private memories
            project_id: Project ID for filtering
            
        Returns:
            Dictionary with keys: user, feedback, project, reference
        """
        # Get all memories
        all_memories = await self.storage.list_all()
        
        # Load full entries
        entries = []
        for m in all_memories:
            entry = await self.storage.get(m.id)
            if entry:
                entries.append(entry)
        
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
        entries: List[MemoryEntry],
        query: str,
    ) -> List[MemoryEntry]:
        """Sort entries by relevance to query."""
        query_words = set(query.lower().split())
        
        def score(entry: MemoryEntry) -> int:
            text = f"{entry.title} {entry.description} {entry.content}".lower()
            return sum(1 for word in query_words if word in text)
        
        return sorted(entries, key=score, reverse=True)
    
    async def format_for_prompt(
        self,
        memories: Dict[str, List[MemoryEntry]],
    ) -> str:
        """
        Format memories for injection into system prompt.
        
        Args:
            memories: Dictionary of memories by type
            
        Returns:
            Formatted string for prompt
        """
        return render_template(
            "memory/context_injection.prompt.j2",
            user_memories=memories.get("user", []),
            feedback_memories=memories.get("feedback", []),
            project_memories=memories.get("project", []),
            reference_memories=memories.get("reference", []),
        )
