"""
Memory System Dependency Injection Container

Provides dependency injection for the memory system to eliminate global singletons
and circular imports. All components are created through this container and
receive their dependencies via constructor injection.
"""

import logging

from app.core.memory.config import MemoryConfig
from app.core.memory.manager import MemoryManager
from app.core.memory.pruning import MemoryPruningService
from app.core.memory.quality import MemoryQualityAnalyzer
from app.core.memory.retrieval import MemoryRetriever
from app.core.memory.short_term import SqlShortTermMemory
from app.core.memory.state_tracking import MemoryStateTracker
from app.core.memory.store import MemoryStore
from app.core.memory.two_tier import TwoTierMemoryManager

logger = logging.getLogger(__name__)


class MemoryContainer:
    """
    Dependency injection container for the memory system.

    This container manages the lifecycle of all memory components,
    eliminating the need for global singletons and making the system
    fully testable with dependency injection.
    """

    def __init__(self, config: MemoryConfig | None = None):
        """
        Initialize the container with configuration.

        Args:
            config: Memory system configuration. If None, uses default config.
        """
        self.config = config or MemoryConfig.from_settings()
        self._initialized = False

        # Components (initialized lazily)
        self._storage: MemoryStore | None = None
        self._short_term: SqlShortTermMemory | None = None
        self._pruning: MemoryPruningService | None = None
        self._smart_retriever: MemoryRetriever | None = None
        self._quality: MemoryQualityAnalyzer | None = None
        self._state_tracker: MemoryStateTracker | None = None
        self._two_tier: TwoTierMemoryManager | None = None
        self._manager: MemoryManager | None = None

    async def initialize(self) -> None:
        """Initialize all components."""
        if self._initialized:
            return

        logger.info("[MemoryContainer] Initializing memory system...")

        # Initialize storage backend
        await self._init_storage()
        await self.storage.initialize()

        # Initialize short-term memory
        await self._init_short_term()

        # Initialize main manager (depends on storage)
        self._manager = MemoryManager(
            config=self.config,
            storage=self.storage,
            short_term=self.short_term,
        )
        await self._manager.initialize()

        self._initialized = True
        logger.info("[MemoryContainer] Memory system initialized")

    async def shutdown(self) -> None:
        """Shutdown all components and release resources."""
        if not self._initialized:
            return

        logger.info("[MemoryContainer] Shutting down memory system...")

        # Note: We do NOT call flush() here because it deletes all data.
        # flush() is only for testing. Here we just release resources
        # and ensure proper cleanup without data loss.

        # Mark as uninitialized
        self._initialized = False
        logger.info("[MemoryContainer] Memory system shutdown complete")

    async def _init_storage(self) -> None:
        """Initialize storage backend."""
        self._storage = MemoryStore(
            str(self.config.user_memory_root),
            project_roots=self.project_roots,
        )

    async def _init_short_term(self) -> None:
        """Initialize short-term memory backend."""
        self._short_term = SqlShortTermMemory()
        await self._short_term.initialize()

    @property
    def project_roots(self) -> dict[int, str]:
        """Mutable mapping of project_id → project memory root path."""
        if not hasattr(self, "_project_roots"):
            self._project_roots: dict[int, str] = {}
        return self._project_roots

    # ==========================================================================
    # Component Access (lazy initialization)
    # ==========================================================================

    @property
    def storage(self) -> MemoryStore:
        """Get storage backend."""
        if self._storage is None:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        return self._storage

    @property
    def short_term(self) -> SqlShortTermMemory:
        """Get short-term memory backend."""
        if self._short_term is None:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        return self._short_term

    @property
    def memory_manager(self) -> MemoryManager:
        """Get main memory manager."""
        if self._manager is None:
            raise RuntimeError("Container not initialized. Call initialize() first.")
        return self._manager

    @property
    def pruning_service(self) -> MemoryPruningService:
        """Get memory pruning service (lazy)."""
        if self._pruning is None:
            # Note: project_context and todo_service will be injected as needed
            # e.g. from the domain services
            self._pruning = MemoryPruningService(storage=self.storage)
        return self._pruning

    @property
    def retrieval_service(self) -> MemoryRetriever:
        """
        Get memory retrieval service (lazy).

        Note: This now returns MemoryRetriever, which combines the functionality
        of legacy retrieval classes.
        """
        if self._smart_retriever is None:
            self._smart_retriever = MemoryRetriever(
                storage=self.storage,
                config=self.config,
            )
        return self._smart_retriever

    @property
    def smart_retriever(self) -> MemoryRetriever:
        """Get smart memory retriever (lazy) - alias for retrieval_service."""
        return self.retrieval_service

    @property
    def quality_analyzer(self) -> MemoryQualityAnalyzer:
        """Get quality analyzer (lazy)."""
        if self._quality is None:
            self._quality = MemoryQualityAnalyzer(
                storage=self.storage,
                config=self.config,
            )
        return self._quality

    @property
    def state_tracker(self) -> MemoryStateTracker:
        """Get state tracker (lazy)."""
        if self._state_tracker is None:
            self._state_tracker = MemoryStateTracker()
        return self._state_tracker

    @property
    def two_tier_manager(self) -> TwoTierMemoryManager:
        """Get two-tier memory manager (lazy)."""
        if self._two_tier is None:
            self._two_tier = TwoTierMemoryManager(
                storage=self.storage,
                config=self.config,
            )
        return self._two_tier
