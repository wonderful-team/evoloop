"""
Unified Memory Manager

The main entry point for all memory operations in EvoLoop.
Provides a unified interface for both embedded and full modes.

Architecture:
- Short-term memory: SQL (SQLite/PostgreSQL) for conversation history
- Long-term memory: File-based (embedded) or Neo4j (full)
- Extraction: Automatic memory extraction from conversations
- Retrieval: LLM-assisted relevance selection

Usage:
    # Recommended way (using MemoryContainer)
    from app.core.memory import MemoryContainer, MemoryConfig
    
    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    manager = container.memory_manager
    
    # Or create manually with dependency injection
    from app.core.memory.config import MemoryConfig
    from app.core.memory.manager import MemoryManager
    from app.core.memory.factory import MemoryFactory
    
    config = MemoryConfig.from_settings()
    storage = MemoryFactory.create_storage(config)
    short_term = MemoryFactory.create_short_term_memory(config)
    manager = MemoryManager(config=config, storage=storage, short_term=short_term)
    await manager.initialize()
"""

import logging
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, ConfigDict
from langchain_core.messages import BaseMessage

from app.core.config import settings
from app.core.memory.models import (
    MemoryEntry,
    MemorySearchResult,
    MemoryType,
    PrivacyLevel,
)
from app.core.memory.backends.file_backend import FileMemoryStorage
from app.core.memory.extraction import MemoryExtractionService, MemoryConsolidationService
from app.core.memory.retrieval import MemoryRetriever
from app.core.memory.interfaces.short_term import IShortTermMemory
from app.core.memory.backends.sql_short_term import SqlShortTermMemory
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class _PreferenceAdapter:
    """Adapter to provide preferences interface on top of new memory system."""
    
    def __init__(self, manager: "MemoryManager"):
        self._manager = manager
    
    async def set_preference(
        self,
        user_id: str,
        key: str,
        value: str,
        description: str = "",
        project_id: int | None = None,
    ) -> None:
        """Save a user preference as a memory entry."""
        entry = MemoryEntry(
            id=f"pref_{user_id}_{key}",
            type=MemoryType.USER,
            privacy=PrivacyLevel.PRIVATE,
            title=f"Preference: {key}",
            content=f"{key}: {value}\n\n{description}",
            description=f"{key} = {value}",
            project_id=project_id,
            user_id=user_id,
            tags=["preference", key],
        )
        await self._manager.save_memory(entry)
    
    async def get_merged_preferences(self, user_id: str, project_id: int | None = None) -> str:
        """Get merged preferences for a user."""
        memories = await self._manager.search_memories(
            query="preference",
            types=[MemoryType.USER],
            privacy=PrivacyLevel.PRIVATE,
            project_id=project_id,
            limit=50,
        )
        
        if not memories:
            return "No specific preferences recorded."
        
        lines = ["**User Preferences:**"]
        for mem in memories:
            if "preference" in mem.tags:
                lines.append(f"- {mem.description}")
        
        return "\n".join(lines) if len(lines) > 1 else "No specific preferences recorded."


class _GraphAdapter:
    """Adapter to provide graph interface on top of new memory system."""
    
    def __init__(self, manager: "MemoryManager"):
        self._manager = manager
    
    async def get_directory_info(self, project_id: int, path: str) -> dict:
        """Get directory info (placeholder for GraphRAG)."""
        # In file-based mode, this is not supported
        return {"summary": "", "sub_modules": [], "dependencies": []}
    
    async def search(self, query: str, limit: int = 5) -> str:
        """Search graph (delegates to memory search)."""
        results = await self._manager.search_memories(query, limit=limit)
        if not results:
            return ""
        lines = [f"- **{r.title}**: {r.description}" for r in results]
        return "\n".join(lines)
    
    async def traverse(self, start_node_id: str, relation_type: str, max_depth: int = 2) -> list:
        """Graph traversal (not supported in file mode)."""
        return []


class _LongTermAdapter:
    """Adapter to provide legacy long_term interface."""
    
    def __init__(self, storage):
        self._storage = storage
    
    # Concept methods
    async def search_concepts(self, query: str, project_id: int | None = None, min_score: float = 0.7):
        """Search concepts (mapped to PROJECT memories)."""
        results = await self._storage.search(
            query=query,
            types=[MemoryType.PROJECT],
            project_id=project_id,
            limit=10,
        )
        # Convert to old SearchResult format
        return [
            type('SearchResult', (), {
                'name': r.title,
                'description': r.description,
                'score': 0.8,
                'files': [],
            })() for r in results
        ]
    
    async def search_concepts_data(self, query: str, project_id: int | None = None) -> list[dict]:
        """Raw concept search."""
        results = await self.search_concepts(query, project_id)
        return [
            {
                'name': r.name,
                'description': r.description,
                'project_id': project_id or 0,
            } for r in results
        ]
    
    async def store_concept(self, concept) -> None:
        """Store a concept as a PROJECT memory."""
        entry = MemoryEntry(
            id=f"concept_{concept.name}",
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title=concept.name,
            content=concept.description,
            description=concept.description[:200],
            project_id=concept.project_id,
            tags=["concept"] + (concept.related_files or []),
        )
        await self._storage.save(entry)
    
    async def list_concepts(self, project_id: int, limit: int = 50) -> list[dict]:
        """List concepts for a project."""
        results = await self._storage.list_all(
            type_filter=MemoryType.PROJECT,
        )
        return [
            {
                'name': r.title,
                'description': r.description,
                'episode_count': 0,
            } for r in results[:limit]
        ]
    
    async def get_project_concepts(self, project_id: int) -> list[str]:
        """Get concepts as strings for a project."""
        results = await self.list_concepts(project_id)
        return [f"{r['name']}: {r['description']}" for r in results]
    
    # Episode methods
    async def record_episode(self, episode) -> str | None:
        """Record an episode as a PROJECT memory.
        
        Format is optimized for readability - combines session summary format
        with detailed plan information.
        """
        import uuid
        
        # Generate unique ID to avoid conflicts
        entry_id = f"session_{episode.source_message_id or uuid.uuid4().hex[:8]}"
        
        # Format content: if result looks like a session summary, use it directly
        # otherwise wrap it in a friendly format
        content = episode.result
        if episode.plan_summary and len(episode.plan_summary) > 20:
            content += f"\n\nExecution Plan:\n{episode.plan_summary}"
        
        # Create a concise title
        goal_short = episode.goal[:60] + "..." if len(episode.goal) > 60 else episode.goal
        
        entry = MemoryEntry(
            id=entry_id,
            type=MemoryType.PROJECT,
            privacy=PrivacyLevel.TEAM,
            title=f"Session: {goal_short}",
            content=content,
            description=episode.result[:200] if episode.result else episode.goal[:200],
            project_id=episode.project_id,
            source_message_id=episode.source_message_id,
            source="session",
            tags=["session", "episode"],
        )
        await self._storage.save(entry)
        logger.info(f"[MemoryManager] Recorded session memory: {entry_id}")
        return entry.id
    
    async def retrieve_experience(self, goal: str, project_id: int, top_k: int = 3) -> str:
        """Retrieve similar experiences."""
        results = await self._storage.search(
            query=goal,
            types=[MemoryType.PROJECT],
            project_id=project_id,
            limit=top_k,
        )
        if not results:
            return ""
        lines = [f"- {r.title}: {r.description}" for r in results]
        return "Past Experiences:\n" + "\n".join(lines)
    
    async def find_episodes_by_concept(self, concept_name: str, project_id: int, limit: int = 10) -> list[dict]:
        """Find episodes by concept."""
        # In file-based mode, we search for project memories tagged with "episode" 
        # or containing the concept name in text search
        results = await self._storage.search(
            query=concept_name,
            types=[MemoryType.PROJECT],
            project_id=project_id,
            limit=limit,
        )
        
        episodes = []
        for r in results:
            if "concept" in r.tags and r.title == concept_name:
                # This is the concept definition itself, not an episode
                continue
                
            # Clean up goal title
            goal = r.title
            if goal.startswith("Episode: "):
                goal = goal[len("Episode: "):]
            
            # Result is stored in content or description 
            # (In trace_recorder.py, we store the summary in description/content)
            # We prefer content as it's the full Markdown body
            result = r.content if (r.content and len(r.content) > 10) else r.description
            if not result:
                result = "No summary available for this execution."
            
            # If the result is a full block, try to keep it all, no truncation here
            episodes.append({
                'id': r.id,
                'goal': goal,
                'result': result,
                'error': None, 
                'timestamp': r.updated_at.isoformat() if hasattr(r, 'updated_at') and r.updated_at else '',
            })
        return episodes
    
    async def link_episode_to_concepts(self, episode_id: str, concept_names: list[str], project_id: int) -> None:
        """Link episode to concepts (no-op in file mode)."""
        pass
    
    async def delete_episodes_by_message_ids(self, message_ids: list[str]) -> int:
        """Delete episodes by message IDs."""
        count = 0
        for msg_id in message_ids:
            # Find and delete
            results = await self._storage.list_all()
            for r in results:
                if r.id == f"ep_{msg_id}":
                    await self._storage.delete(r.id)
                    count += 1
        return count
    
    async def delete_episodes_by_run_ids(self, run_ids: list[str]) -> int:
        """Delete episodes by run IDs."""
        return await self.delete_episodes_by_message_ids(run_ids)
    
    # Passthrough methods
    async def search(self, query: str, **kwargs):
        return await self._storage.search(query, **kwargs)
    
    async def save(self, entry: MemoryEntry):
        return await self._storage.save(entry)


class MemoryManager:
    """
    Unified facade for the memory system.
    
    Provides a single entry point for all memory operations:
    - Short-term: Conversation history (SQL)
    - Long-term: Persistent knowledge (File or Neo4j)
    - Extraction: Automatic memory creation
    - Retrieval: Smart memory selection
    
    Usage:
        # Using MemoryContainer (recommended)
        from app.core.memory import MemoryContainer, MemoryConfig
        
        container = MemoryContainer(MemoryConfig.from_settings())
        await container.initialize()
        manager = container.memory_manager
        
        # Or create manually with dependency injection
        from app.core.memory.config import MemoryConfig
        from app.core.memory.manager import MemoryManager
        from app.core.memory.factory import MemoryFactory
        
        config = MemoryConfig.from_settings()
        storage = MemoryFactory.create_storage(config)
        short_term = MemoryFactory.create_short_term_memory(config)
        manager = MemoryManager(config=config, storage=storage, short_term=short_term)
        await manager.initialize()
    """
    
    def __init__(
        self,
        config: Optional['MemoryConfig'] = None,
        storage: Optional[FileMemoryStorage] = None,
        short_term: Optional[IShortTermMemory] = None,
    ):
        """
        Initialize memory manager with appropriate backends.
        
        Args:
            config: Memory configuration. If None, uses default from settings.
            storage: Storage backend. If None, creates based on config.
            short_term: Short-term memory backend. If None, creates SqlShortTermMemory.
        """
        # Import here to avoid circular imports at module level
        from app.core.memory.config import MemoryConfig
        
        self.config = config or MemoryConfig.from_settings()
        
        # Short-term memory (always SQL)
        if short_term is not None:
            self.short_term = short_term
        else:
            self.short_term: IShortTermMemory = SqlShortTermMemory()
        
        # Long-term memory backend
        if storage is not None:
            self._storage = storage
            logger.info(f"MemoryManager: Using provided storage backend")
        elif settings.EMBEDDED_MODE:
            # File-based storage for embedded mode
            self._storage = FileMemoryStorage()
            logger.info("MemoryManager: Initialized with FileBackend (embedded mode)")
        else:
            # Neo4j for full mode
            try:
                from app.core.memory.backends.neo4j_backend import Neo4jMemoryStorage
                self._storage = Neo4jMemoryStorage()
                logger.info("MemoryManager: Initialized with Neo4jBackend (full mode)")
            except ImportError:
                # Fallback to file if Neo4j not available
                self._storage = FileMemoryStorage()
                logger.warning("MemoryManager: Neo4j not available, falling back to FileBackend")
        
        # Legacy adapters for backward compatibility
        self.long_term = _LongTermAdapter(self._storage)
        self.preferences = _PreferenceAdapter(self)
        self.graph = _GraphAdapter(self)
        
        # Services (use storage directly)
        self.extraction = MemoryExtractionService(self._storage, config=self.config)
        self.consolidation = MemoryConsolidationService(self._storage)
        self.retrieval = MemoryRetriever(self._storage, config=self.config)
    
    async def initialize(self) -> None:
        """Initialize all memory components."""
        await self.short_term.initialize()
        # File/Neo4j backends initialize lazily
        logger.info("MemoryManager: All components initialized")
    
    async def flush(self) -> None:
        """Flush all memory components (for testing)."""
        await self.short_term.flush()
        # FileMemoryStorage is stateless and doesn't need flush
        # Neo4j backend would have flush() if needed
        if hasattr(self._storage, 'flush'):
            await self._storage.flush()
        logger.info("MemoryManager: All components flushed")
    
    # ========================================================================
    # Short-term Memory Operations
    # ========================================================================
    
    async def add_message(self, thread_id: str, message: BaseMessage) -> None:
        """
        Add a message to the conversation history.
        
        Args:
            thread_id: Conversation thread identifier
            message: The message to store
        """
        await self.short_term.add_message(thread_id, message)
    
    async def get_context(
        self,
        thread_id: str,
        limit: int = 50,
    ) -> List[BaseMessage]:
        """
        Retrieve recent conversation context.
        
        Args:
            thread_id: Conversation thread identifier
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of messages in chronological order
        """
        return await self.short_term.get_context(thread_id, limit)
    
    async def search_messages(
        self,
        query: str,
        thread_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[BaseMessage]:
        """
        Search conversation history.
        
        Args:
            query: Search query
            thread_id: Optional thread ID to narrow search
            limit: Maximum results
            
        Returns:
            List of matching messages
        """
        return await self.short_term.search_messages(query, thread_id, limit)
    
    # ========================================================================
    # Long-term Memory Operations
    # ========================================================================
    
    async def save_memory(self, entry: MemoryEntry) -> None:
        """
        Save a memory entry to long-term storage.
        
        Also appends to daily log for KAIROS consolidation.
        
        Args:
            entry: Memory entry to save
        """
        await self._storage.save(entry)
        
        # KAIROS: Append to daily log for nightly consolidation
        try:
            from app.core.memory.daily_log import daily_log_writer
            await daily_log_writer.append(entry)
        except Exception as e:
            # Log but don't fail the save
            logger.warning(f"[MemoryManager] Failed to append to daily log: {e}")
    
    async def get_memory(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        Get a memory entry by ID.
        
        Args:
            entry_id: Memory entry ID
            
        Returns:
            Memory entry or None if not found
        """
        return await self._storage.get(entry_id)
    
    async def delete_memory(self, entry_id: str) -> bool:
        """
        Delete a memory entry.
        
        Args:
            entry_id: Memory entry ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        return await self._storage.delete(entry_id)
    
    async def search_memories(
        self,
        query: str,
        types: Optional[List[MemoryType]] = None,
        privacy: Optional[PrivacyLevel] = None,
        project_id: Optional[int] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """
        Search long-term memories.
        
        Args:
            query: Search query text
            types: Filter by memory types
            privacy: Filter by privacy level
            project_id: Filter by project ID
            limit: Maximum number of results
            
        Returns:
            List of matching memory entries
        """
        return await self._storage.search(
            query=query,
            types=types,
            privacy=privacy,
            project_id=project_id,
            limit=limit,
        )
    
    # ========================================================================
    # Two-Tier Memory Operations
    # ========================================================================
    
    async def get_hot_memory(self) -> str:
        """
        Get Tier 1 hot memory (MEMORY.md).
        
        This is always loaded at session start. Contains the most
        important project knowledge ranked by importance.
        
        Returns:
            MEMORY.md content (truncated if exceeds limits)
        """
        from app.core.memory.two_tier import TwoTierMemoryManager
        two_tier = TwoTierMemoryManager(storage=self._storage, config=self.config)
        return await two_tier.get_hot_memory()
    
    async def search_cold_memory(
        self,
        query: str,
        max_results: int = 5,
    ) -> List[MemoryEntry]:
        """
        Search Tier 2 cold memory (full storage).
        
        This is searched on demand when hot memory is insufficient.
        Uses smart retrieval for semantic relevance.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of relevant memory entries
        """
        from app.core.memory.two_tier import TwoTierMemoryManager
        two_tier = TwoTierMemoryManager(storage=self._storage, config=self.config)
        return await two_tier.search_cold_memory(query, max_results)
    
    async def regenerate_memory_md(self) -> None:
        """
        Regenerate MEMORY.md from cold memory.
        
        This updates the hot memory (Tier 1) based on the current
        state of cold memory (Tier 2), applying budgets and rankings.
        """
        from app.core.memory.two_tier import TwoTierMemoryManager
        two_tier = TwoTierMemoryManager(storage=self._storage, config=self.config)
        await two_tier.regenerate_memory_md()
    
    async def list_memories(
        self,
        type_filter: Optional[MemoryType] = None,
        privacy_filter: Optional[PrivacyLevel] = None,
        limit: Optional[int] = None,
    ) -> List[MemorySearchResult]:
        """
        List all memories (lightweight).

        Args:
            type_filter: Filter by type
            privacy_filter: Filter by privacy
            limit: Maximum number of results

        Returns:
            List of memory search results
        """
        return await self._storage.list_all(type_filter, privacy_filter, limit)
    
    async def get_recent_memories(self, count: int = 5) -> List[MemoryEntry]:
        """
        Get most recently updated memories.

        Args:
            count: Number of entries to return

        Returns:
            List of recent memory entries
        """
        return await self._storage.get_recent(count)


class CheckpointDedupResult(DynamicBaseModel):
    """Result of a checkpoint deduplication operation."""
    dry_run: bool = True
    total_checkpoints: int = 0
    duplicate_groups: int = 0
    duplicates_found: int = 0
    duplicates_removed: int = 0
    bytes_saved: int = 0
    elapsed_ms: int = 0
    error: Optional[str] = None

    async def deduplicate_checkpoints(self, dry_run: bool = True) -> "CheckpointDedupResult":
        """
        Remove duplicate checkpoint memories from storage.

        Only works with FileMemoryStorage backend. For other backends,
        returns empty result.

        Args:
            dry_run: If True, only report duplicates without deleting

        Returns:
            Dict with deduplication stats
        """
        if isinstance(self._storage, FileMemoryStorage):
            return await self._storage.deduplicate_checkpoints(dry_run)
        else:
            logger.warning("[MemoryManager] deduplicate_checkpoints only supported for FileMemoryStorage")
            return CheckpointDedupResult(
                dry_run=dry_run,
                total_checkpoints=0,
                duplicate_groups=0,
                duplicates_found=0,
                duplicates_removed=0,
                bytes_saved=0,
                elapsed_ms=0,
                error="Not supported for this storage backend"
            )

    # ========================================================================
    # Extraction Operations
    # ========================================================================
    
    async def extract_memories(
        self,
        thread_id: str,
        messages: List[BaseMessage],
        project_id: Optional[int] = None,
        user_id: Optional[str] = None,
    ) -> List[MemoryEntry]:
        """
        Automatically extract memories from a conversation.
        
        Args:
            thread_id: Conversation thread ID
            messages: List of conversation messages
            project_id: Associated project ID
            user_id: User ID
            
        Returns:
            List of extracted memory entries
        """
        return await self.extraction.extract_from_conversation(
            thread_id=thread_id,
            messages=messages,
            project_id=project_id,
            user_id=user_id,
        )
    
    async def consolidate_memory(
        self,
        working_content: str,
        source: str = "consolidated",
    ) -> Optional[MemoryEntry]:
        """
        Consolidate working memory into long-term storage.
        
        Args:
            working_content: Content from working memory
            source: Source tag
            
        Returns:
            Created memory entry or None
        """
        return await self.consolidation.consolidate(working_content, source)
    
    # ========================================================================
    # Retrieval Operations
    # ========================================================================
    
    async def find_relevant_memories(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        max_results: int = 5,
    ) -> List[MemoryEntry]:
        """
        Find memories relevant to the current query.
        
        Uses LLM-assisted relevance selection (Claude Code style).
        
        Args:
            query: User query
            context: Additional context (tools used, etc.)
            max_results: Maximum number of results
            
        Returns:
            List of relevant memory entries
        """
        return await self.retrieval.find_relevant(
            query=query,
            context=context,
            max_results=max_results,
        )
    
    async def get_context_memories(
        self,
        query: str,
        user_id: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> Dict[str, List[MemoryEntry]]:
        """
        Get memories organized by type for context injection.
        
        Args:
            query: Current query
            user_id: User ID for private memories
            project_id: Project ID for filtering
            
        Returns:
            Dictionary with memories grouped by type
        """
        return await self.retrieval.get_for_context_injection(
            query=query,
            user_id=user_id,
            project_id=project_id,
        )


# Note: Global singleton removed. Use MemoryContainer or create instance manually.
# Example:
#   from app.core.memory import MemoryContainer, MemoryConfig
#   container = MemoryContainer(MemoryConfig.from_settings())
#   await container.initialize()
#   manager = container.memory_manager
