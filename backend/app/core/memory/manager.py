"""
Unified Memory Manager

The main entry point for all memory operations in EvoLoop.
Provides a unified interface for both embedded and full modes.

Architecture:
- Short-term memory: SQL (SQLite/PostgreSQL) for conversation history
- Long-term memory: File-based (embedded) or Neo4j (full)
- Extraction: Automatic memory extraction from conversations
- Retrieval: LLM-assisted relevance selection
"""

import logging
from typing import Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.engine.message.native_classes import BaseMessage
from app.core.file import compute_sha256
from app.core.memory.config import MemoryConfig
from app.core.memory.interfaces import IShortTermMemory
from app.core.memory.models import (
    MemoryEntry,
    MemorySearchResult,
    MemoryType,
    PrivacyLevel,
)
from app.core.memory.retrieval import MemoryRetriever
from app.core.memory.schemas import CheckpointDedupResult, Concept, Episode
from app.core.memory.short_term import SqlShortTermMemory
from app.core.memory.store import MemoryStore
from app.utils.id import gen_uuid_hex

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Unified facade for the memory system.

    Provides a single entry point for all memory operations:
    - Short-term: Conversation history (SQL)
    - Long-term: Persistent knowledge (File or Neo4j)
    - Extraction: Automatic memory creation
    - Retrieval: Smart memory selection
    """

    MAINTENANCE_THRESHOLD = 50  # Only run pruning/consolidation when library reaches this scale

    def __init__(
        self,
        config: "MemoryConfig | None" = None,
        storage: MemoryStore | None = None,
        short_term: IShortTermMemory | None = None,
    ):
        """
        Initialize memory manager with appropriate backends.

        Args:
            config: Memory configuration. If None, uses default from settings.
            storage: Storage backend. If None, creates based on EMBEDDED_MODE.
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
            logger.info("MemoryManager: Using provided storage backend")
        else:
            self._storage = MemoryStore()
            mode = "embedded" if settings.EMBEDDED_MODE else "full"
            logger.info(f"MemoryManager: Initialized with MemoryStore ({mode} mode)")

        # Services (use storage directly)
        from app.core.memory.pruning import MemoryPruningService
        from app.core.memory.quality import MemoryQualityAnalyzer

        self.pruning = MemoryPruningService(self._storage)
        self.retrieval = MemoryRetriever(self._storage, config=self.config)
        self.quality = MemoryQualityAnalyzer(self._storage, config=self.config)

    async def initialize(self) -> None:
        """Initialize all memory components."""
        await self.short_term.initialize()
        await self._storage.initialize()
        logger.info("MemoryManager: All components initialized")

    async def flush(self) -> None:
        """Flush all memory components (for testing)."""
        await self.short_term.flush()
        if hasattr(self._storage, "flush"):
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
    ) -> list[BaseMessage]:
        """
        Retrieve recent conversation context.

        Args:
            thread_id: Conversation thread identifier
            limit: Maximum number of messages to retrieve

        Returns:
            List of messages in chronological order
        """
        return await self.short_term.get_context(thread_id, limit)

    # ========================================================================
    # User Preferences (Direct Methods)
    # ========================================================================

    async def save_preference(
        self,
        member_id: int,
        key: str,
        value: str,
        description: str = "",
        project_id: int | None = None,
    ) -> None:
        """Save a user preference as a MemoryEntry."""
        entry = MemoryEntry(
            id=f"pref_{member_id}_{key}",
            type=MemoryType.USER,
            privacy=PrivacyLevel.PRIVATE,
            title=f"Preference: {key}",
            content=f"{key}: {value}\n\n{description}",
            description=f"{key} = {value}",
            project_id=project_id,
            member_id=member_id,
            tags=["preference", key],
        )
        await self.save_memory(entry)

    async def get_merged_preferences(self, member_id: int, project_id: int | None = None) -> str:
        """Get merged preferences formatted for LLM context."""
        memories = await self.search_memories(
            query="preference",
            types=[MemoryType.USER],
            privacy=PrivacyLevel.PRIVATE,
            project_id=project_id,
            limit=50,
            member_id=member_id,
        )

        if not memories:
            return "No specific preferences recorded."

        lines = ["**User Preferences:**"]
        for mem in memories:
            if "preference" in mem.tags:
                lines.append(f"- {mem.description}")

        return "\n".join(lines) if len(lines) > 1 else "No specific preferences recorded."

    # ========================================================================
    # Knowledge & Concepts (Unified Facade)
    # ========================================================================

    async def store_concept(
        self,
        concept: Concept | str,
        description: str | None = None,
        project_id: int | None = DEFAULT_PROJECT_ID,
        related_files: list[str] | None = None,
        member_id: int = 0,
        source_message_id: str | None = None,
        source_thread_id: str | None = None,
        created_by_member_id: int | None = None,
        memory_kind: str = "concept",
    ) -> MemoryEntry:
        """
        Store a domain concept.
        """
        # Normalize input to Concept model
        if isinstance(concept, str):
            concept_obj = Concept(
                name=concept,
                description=description or "",
                project_id=project_id,
                related_files=related_files or [],
            )
        else:
            concept_obj = concept

        entry = MemoryEntry(
            id=f"concept_{concept_obj.name.lower().replace(' ', '_')}",
            type=MemoryType.CONCEPT,
            privacy=PrivacyLevel.TEAM,
            title=concept_obj.name,
            content=concept_obj.description,
            description=concept_obj.description[:200],
            project_id=concept_obj.project_id,
            member_id=member_id,
            created_by_member_id=created_by_member_id or member_id,
            memory_kind=memory_kind,
            tags=["concept"] + concept_obj.related_files,
            source_message_id=source_message_id,
            source_thread_id=source_thread_id,
        )
        await self.save_memory(entry)
        return entry

    async def search_concepts(
        self,
        query: str,
        project_id: int | None = None,
        limit: int = 10,
        member_id: int = 0,
    ) -> list[Concept]:
        """
        Search for domain concepts.
        """
        entries = await self.search_memories(
            query=query,
            types=[MemoryType.CONCEPT],
            project_id=project_id,
            member_id=member_id,
            limit=limit,
        )
        return [
            Concept(name=e.title, description=e.content, related_files=e.tags, source_thread_id=e.source_thread_id)
            for e in entries
        ]

    async def search_concepts_data(
        self,
        query: str,
        project_id: int | None = None,
        limit: int = 10,
        member_id: int = 0,
    ) -> list[dict]:
        """
        Search for domain concepts and return raw data.
        """
        concepts = await self.search_concepts(query, project_id, limit, member_id)
        return [
            {"name": c.name, "description": c.description, "project_id": c.project_id}
            for c in concepts
        ]

    async def get_project_concepts(self, project_id: int) -> list[str]:
        """Get all concepts for a project as formatted strings."""
        results = await self.list_memories(type_filter=MemoryType.CONCEPT, limit=100)
        return [f"{m.title}: {m.description}" for m in results]

    async def find_episodes_by_concept(
        self,
        concept_name: str,
        project_id: int | None = None,
        limit: int = 10,
        member_id: int = 0,
    ) -> list[dict]:
        """Find all episodes linked to a specific concept."""
        return []

    async def get_concept_episode_counts_batch(self, project_id: int | None = None, member_id: int = 0) -> dict[str, int]:
        """Efficiently get counts for all concepts in one go."""
        return {}

    # ========================================================================
    # Episode Recording
    # ========================================================================

    async def record_episode(self, episode: Episode) -> str:
        """
        Record a task episode.
        """
        source_message_id = episode.source_message_id
        project_id = episode.project_id
        goal = episode.goal
        outcome = episode.result

        entry_id = f"ep_{source_message_id or gen_uuid_hex()[:8]}"
        goal_short = goal[:60] + "..." if len(goal) > 60 else goal

        entry = MemoryEntry(
            id=entry_id,
            type=MemoryType.EPISODE,
            privacy=PrivacyLevel.TEAM,
            title=f"Episode: {goal_short}",
            content=f"Goal: {goal}\nOutcome: {outcome}",
            description=outcome[:200],
            project_id=project_id,
            member_id=episode.member_id or 0,
            source_message_id=source_message_id,
            source="episode_recording",
            tags=["episode"],
        )
        await self.save_memory(entry)
        return entry_id

    async def search_episodes(
        self,
        query: str,
        project_id: int | None = None,
        limit: int = 5,
        member_id: int = 0,
    ) -> list[dict]:
        """Search for execution episodes."""
        results = await self.search_memories(
            query=query,
            types=[MemoryType.EPISODE],
            project_id=project_id,
            member_id=member_id,
            limit=limit,
        )
        return [
            {
                "id": r.id,
                "goal": r.title.replace("Episode: ", ""),
                "result": r.content,
                "timestamp": r.updated_at.isoformat() if r.updated_at else "",
            }
            for r in results
        ]

    async def retrieve_experience(self, goal: str, project_id: int, top_k: int = 3, member_id: int = 0) -> str:
        """Find past episodes similar to the current goal."""
        episodes = await self.search_episodes(goal, project_id, limit=top_k, member_id=member_id)
        if not episodes:
            return ""

        lines = ["### Past Experiences:", ""]
        for ep in episodes:
            lines.append(f"- **Goal**: {ep['goal']}")
            lines.append(f"  **Result**: {ep['result'][:200]}...")
            lines.append("")
        return "\n".join(lines)

    async def get_directory_info(self, project_id: int, path: str) -> dict:
        """Retrieve architectural summary for a directory."""
        return {
            "path": path,
            "summary": "No summary available (Directory not indexed or graph backend not configured).",
            "sub_modules": [],
            "dependencies": [],
        }

    # ========================================================================
    # Long-term Memory Operations
    # ========================================================================

    async def save_memory(self, entry: MemoryEntry) -> None:
        """Save a memory entry."""
        await self._storage.save(entry)

    async def ingest_project_profile(self, project_id: int, content: str, member_id: int = 0) -> None:
        """
        Ingest PROJECT.md content into the memory system as a PROJECT-type entry.

        This makes the project's self-description searchable via search_memories/recall.
        Deduplicates by content_hash; updates existing entry if content changes.
        """
        entry_id = f"project_md_{project_id}"
        content_hash = compute_sha256(content)

        # Check if existing entry has same content (skip if unchanged)
        existing = await self.get_memory(entry_id)
        if existing and existing.content_hash == content_hash:
            return

        entry = MemoryEntry(
            id=entry_id,
            type=MemoryType.PROJECT,
            title=f"PROJECT.md (project {project_id})",
            content=content,
            content_hash=content_hash,
            project_id=project_id,
            member_id=member_id,
            source_file_path="PROJECT.md",
            tags=["project_profile", "auto_ingested"],
        )
        await self._storage.save(entry)
        logger.info(f"[MemoryManager] Ingested PROJECT.md for project {project_id} ({len(content)} chars)")

    async def delete_memory(self, entry_id: str) -> bool:
        """Permanently delete a memory entry by ID."""
        return await self._storage.delete(entry_id)

    async def delete(self, entry_id: str) -> bool:
        """Alias for delete_memory for tool/manager consistency."""
        return await self._storage.delete(entry_id)

    async def get_memory(self, entry_id: str) -> MemoryEntry | None:
        """
        Get a memory entry by ID.

        Args:
            entry_id: Memory entry ID

        Returns:
            Memory entry or None if not found
        """
        return await self._storage.get(entry_id)

    async def search_memories(
        self,
        query: str,
        types: list[MemoryType] | None = None,
        privacy: PrivacyLevel | None = None,
        project_id: int | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 10,
        member_id: int = 0,
    ) -> list[MemoryEntry]:
        """
        Search long-term memories.

        Args:
            query: Search query text
            types: Filter by memory types
            privacy: Filter by privacy level
            project_id: Filter by project ID
            filters: Structured metadata filters
            limit: Maximum number of results

        Returns:
            List of matching memory entries
        """
        return await self._storage.search(
            query=query,
            types=types,
            privacy=privacy,
            project_id=project_id,
            filters=filters,
            limit=limit,
            member_id=member_id,
        )

    async def find_by_hash(self, content_hash: str, project_id: int | None = None) -> MemoryEntry | None:
        """
        Find a memory entry by its content hash.

        Args:
            content_hash: SHA-256 hash of the content
            project_id: Optional project scope

        Returns:
            Matching MemoryEntry or None
        """
        return await self._storage.find_by_hash(content_hash, project_id)

    # ========================================================================
    # Two-Tier Memory Operations
    # ========================================================================

    async def get_hot_memory(self, project_id: int | None = None) -> str:
        """
        Get Tier 1 hot memory (MEMORY.md).

        This is always loaded at session start. Contains the most
        important project knowledge ranked by importance.

        Returns:
            MEMORY.md content (truncated if exceeds limits)
        """
        memory_root = None
        if project_id:
            try:
                from app.core.project.utils import get_memory_path, get_project_path

                project_path = await get_project_path(project_id)
                if project_path:
                    memory_root = get_memory_path(project_path)
                    self._storage.project_roots[project_id] = str(memory_root)
            except (
                ValueError,
                OSError,
                RuntimeError,
                TypeError,
                KeyError,
                AttributeError,
            ) as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        from app.core.memory.two_tier import TwoTierMemoryManager

        two_tier = TwoTierMemoryManager(
            storage=self._storage,
            config=self.config,
            analyzer=self.quality,
            root_path=memory_root,
            project_id=project_id,
        )
        return await two_tier.get_hot_memory()

    async def search_cold_memory(
        self,
        query: str,
        max_results: int = 5,
    ) -> list[MemoryEntry]:
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

        two_tier = TwoTierMemoryManager(
            storage=self._storage, config=self.config, analyzer=self.quality
        )
        return await two_tier.search_cold_memory(query, max_results)

    async def regenerate_memory_md(self, project_id: int | None = None) -> None:
        """
        Regenerate MEMORY.md from cold memory.

        This updates the hot memory (Tier 1) based on the current
        state of cold memory (Tier 2), applying budgets and rankings.
        """
        memory_root = None
        if project_id:
            try:
                from app.core.project.utils import get_memory_path, get_project_path

                project_path = await get_project_path(project_id)
                if project_path:
                    memory_root = get_memory_path(project_path)
                    self._storage.project_roots[project_id] = str(memory_root)
            except (ValueError, OSError, RuntimeError, TypeError, KeyError) as e:
                logger.debug("Suppressed error: %s", e, exc_info=True)

        from app.core.memory.two_tier import TwoTierMemoryManager

        two_tier = TwoTierMemoryManager(
            storage=self._storage,
            config=self.config,
            analyzer=self.quality,
            root_path=memory_root,
            project_id=project_id,
        )
        await two_tier.regenerate_memory_md()

    async def list_memories(
        self,
        type_filter: MemoryType | None = None,
        privacy_filter: PrivacyLevel | None = None,
        project_id: int | None = None,
        limit: int | None = None,
        member_id: int = 0,
    ) -> list[MemorySearchResult]:
        """
        List memories (lightweight).

        Args:
            type_filter: Filter by type
            privacy_filter: Filter by privacy
            project_id: Filter by project ID
            limit: Maximum number of results

        Returns:
            List of memory search results
        """
        return await self._storage.list_all(
            type_filter=type_filter,
            privacy_filter=privacy_filter,
            project_id=project_id,
            limit=limit,
            member_id=member_id,
        )

    async def get_recent_memories(
        self,
        count: int = 5,
        project_id: int | None = None,
    ) -> list[MemoryEntry]:
        """
        Get most recently updated memories.

        Args:
            count: Number of entries to return
            project_id: Optional project filter

        Returns:
            List of recent memory entries
        """
        return await self._storage.get_recent(count, project_id=project_id)

    async def deduplicate_checkpoints(self, dry_run: bool = True) -> "CheckpointDedupResult":
        """
        Remove duplicate checkpoint memories from storage.

        Only supported when the underlying storage engine implements
        deduplicate_checkpoints. Returns empty result otherwise.

        Args:
            dry_run: If True, only report duplicates without deleting

        Returns:
            Dict with deduplication stats
        """
        if hasattr(self._storage, "deduplicate_checkpoints"):
            return await self._storage.deduplicate_checkpoints(dry_run)
        else:
            logger.warning("[MemoryManager] deduplicate_checkpoints not supported by current storage backend")
            return CheckpointDedupResult(
                dry_run=dry_run,
                total_checkpoints=0,
                duplicate_groups=0,
                duplicates_found=0,
                duplicates_removed=0,
                bytes_saved=0,
                elapsed_ms=0,
                error="Not supported for this storage backend",
            )

    # ========================================================================
    # Extraction Operations
    # ========================================================================
    # NOTE: Memory extraction is handled by the event bus pipeline:
    #   AuditService → EXTRACTION_REQUESTED event → subscribers.py → save_memory()
    # The AutoMemoryExtractor (auto_extraction.py) has been removed as dead code.

    async def run_maintenance(self, project_id: int | None = None, force: bool = False) -> dict:
        """
        Run system maintenance: Pruning and Consolidation.

        Decision: Only runs when memory count exceeds threshold, or if forced.
        """
        from datetime import datetime

        # Check threshold
        memories = await self.list_memories(limit=self.MAINTENANCE_THRESHOLD + 5)
        count = len(memories)

        if count < self.MAINTENANCE_THRESHOLD and not force:
            logger.info(f"[MemoryManager] Skipping maintenance: current count {count} < threshold {self.MAINTENANCE_THRESHOLD}")
            return {"status": "skipped", "count": count}

        logger.info(f"[MemoryManager] Starting governance cycle (count: {count})")

        # 1. Quality Analysis — identify low-quality / stale memories
        recommendations = await self.quality.get_cleanup_recommendations(
            project_id=project_id,
            min_quality=0.3,
        )
        low_quality_count = len(recommendations)

        # 2. Pruning & Semantic Consolidation
        pruning_logs = await self.pruning.run_pruning_cycle(project_id=project_id)

        # 3. Regenerate Hot Memory (MEMORY.md)
        await self.regenerate_memory_md()

        return {
            "status": "completed",
            "low_quality_count": low_quality_count,
            "pruning_count": len(pruning_logs),
            "logs": pruning_logs,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def find_relevant_memories(
        self,
        query: str,
        context: dict[str, Any] | None = None,
        max_results: int = 5,
    ) -> list[MemoryEntry]:
        """
        Find memories relevant to the current query.
        """
        return await self.retrieval.find_relevant(
            query=query,
            context=context,
            max_results=max_results,
        )
