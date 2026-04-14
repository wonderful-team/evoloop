"""
Memory System Dependency Injection Container

Provides dependency injection for the memory system to eliminate global singletons
and circular imports. All components are created through this container and
receive their dependencies via constructor injection.

Usage:
    # Production
    from app.core.memory.config import MemoryConfig
    from app.core.memory.container import MemoryContainer
    
    config = MemoryConfig.from_settings()
    container = MemoryContainer(config)
    await container.initialize()
    
    # Use components
    manager = container.memory_manager
    extractor = container.auto_extractor
    
    # Cleanup
    await container.shutdown()

    # Testing with custom config
    config = MemoryConfig(memory_root=temp_dir, backend_type="file")
    container = MemoryContainer(config)
"""

import logging

from app.core.memory.auto_extraction import AutoMemoryExtractor
from app.core.memory.backends.file_backend import FileMemoryStorage
from app.core.memory.backends.sql_short_term import SqlShortTermMemory
from app.core.memory.config import MemoryConfig
from app.core.memory.daily_log import DailyLogWriter, LogConsolidator
from app.core.memory.extraction import (
    MemoryConsolidationService,
    MemoryExtractionService,
)
from app.core.memory.interfaces.storage import IMemoryStorage
from app.core.memory.manager import MemoryManager
from app.core.memory.quality import MemoryQualityAnalyzer
from app.core.memory.retrieval import MemoryRetriever
from app.core.memory.state_tracking import MemoryStateTracker
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
        self.config = config or MemoryConfig()
        self._initialized = False

        # Components (initialized lazily)
        self._storage: IMemoryStorage | None = None
        self._short_term: SqlShortTermMemory | None = None
        self._extraction: MemoryExtractionService | None = None
        self._consolidation: MemoryConsolidationService | None = None
        self._smart_retriever: MemoryRetriever | None = None
        self._quality: MemoryQualityAnalyzer | None = None
        self._state_tracker: MemoryStateTracker | None = None
        self._daily_log: DailyLogWriter | None = None
        self._log_consolidator: LogConsolidator | None = None
        self._two_tier: TwoTierMemoryManager | None = None
        self._auto_extractor: AutoMemoryExtractor | None = None
        self._manager: MemoryManager | None = None

    async def initialize(self) -> None:
        """Initialize all components."""
        if self._initialized:
            return

        logger.info("[MemoryContainer] Initializing memory system...")

        # Initialize storage backend
        await self._init_storage()

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
        if self.config.is_file_backend:
            self._storage = FileMemoryStorage(str(self.config.memory_root))
        else:
            # Neo4j backend would be initialized here
            raise NotImplementedError("Neo4j backend not yet supported in DI container")

    async def _init_short_term(self) -> None:
        """Initialize short-term memory backend."""
        self._short_term = SqlShortTermMemory()
        await self._short_term.initialize()

    # ==========================================================================
    # Component Access (lazy initialization)
    # ==========================================================================

    @property
    def storage(self) -> IMemoryStorage:
        """Get storage backend (IMemoryStorage interface)."""
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
    def extraction_service(self) -> MemoryExtractionService:
        """Get memory extraction service (lazy)."""
        if self._extraction is None:
            self._extraction = MemoryExtractionService(
                storage=self.storage,
                config=self.config,
            )
        return self._extraction

    @property
    def consolidation_service(self) -> MemoryConsolidationService:
        """Get memory consolidation service (lazy)."""
        if self._consolidation is None:
            self._consolidation = MemoryConsolidationService(
                storage=self.storage,
            )
        return self._consolidation

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
    def daily_log_writer(self) -> DailyLogWriter:
        """Get daily log writer (lazy)."""
        if self._daily_log is None:
            self._daily_log = DailyLogWriter(
                root_path=self.config.memory_root,
            )
        return self._daily_log

    @property
    def log_consolidator(self) -> LogConsolidator:
        """Get log consolidator (lazy)."""
        if self._log_consolidator is None:
            self._log_consolidator = LogConsolidator(
                root_path=self.config.memory_root,
            )
        return self._log_consolidator

    @property
    def two_tier_manager(self) -> TwoTierMemoryManager:
        """Get two-tier memory manager (lazy)."""
        if self._two_tier is None:
            self._two_tier = TwoTierMemoryManager(
                storage=self.storage,
                config=self.config,
            )
        return self._two_tier

    @property
    def auto_extractor(self) -> AutoMemoryExtractor:
        """Get auto memory extractor (lazy)."""
        if self._auto_extractor is None:
            self._auto_extractor = AutoMemoryExtractor(
                memory_manager=self.memory_manager,
                config=self.config,
            )
        return self._auto_extractor


# Global container instance (for backward compatibility during migration)
# In new code, create and manage your own container instances
_container: MemoryContainer | None = None


def get_container(config: MemoryConfig | None = None) -> MemoryContainer:
    """
    Get or create the global container instance.
    
    This is provided for backward compatibility. New code should create
    and manage their own container instances for better testability.
    
    Usage:
        # Old way (discouraged)
        from app.core.memory.container import get_container
        container = get_container()
        
        # New way (preferred)
        from app.core.memory.config import MemoryConfig
        from app.core.memory.container import MemoryContainer
        container = MemoryContainer(MemoryConfig.from_settings())
    """
    global _container
    if _container is None:
        _container = MemoryContainer(config)
    return _container


def reset_container() -> None:
    """Reset the global container (useful for testing)."""
    global _container
    _container = None
