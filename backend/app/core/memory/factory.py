"""
Memory System Factory

Provides factory methods for creating memory system components.
This simplifies component creation and ensures consistent initialization.

Usage:
    from app.core.memory.config import MemoryConfig
    from app.core.memory.factory import MemoryFactory
    
    # Create with default config
    config = MemoryConfig.from_settings()
    manager = MemoryFactory.create_manager(config)
    
    # Create specific components
    storage = MemoryFactory.create_storage(config)
    extractor = MemoryFactory.create_extractor(config, storage)
"""

import logging
from pathlib import Path
from typing import Optional

from app.core.memory.config import MemoryConfig
from app.core.memory.manager import MemoryManager
from app.core.memory.backends.file_backend import FileMemoryStorage
from app.core.memory.backends.neo4j_backend import Neo4jMemoryStorage
from app.core.memory.backends.sql_short_term import SqlShortTermMemory
from app.core.memory.extraction import MemoryExtractionService, MemoryConsolidationService
from app.core.memory.retrieval import MemoryRetrievalService
from app.core.memory.smart_retrieval import SmartMemoryRetriever
from app.core.memory.quality import MemoryQualityAnalyzer
from app.core.memory.state_tracking import MemoryStateTracker
from app.core.memory.daily_log import DailyLogWriter, LogConsolidator
from app.core.memory.two_tier import TwoTierMemoryManager
from app.core.memory.auto_extraction import AutoMemoryExtractor

logger = logging.getLogger(__name__)


class MemoryFactory:
    """
    Factory for creating memory system components.
    
    This factory centralizes component creation logic and ensures
    that components are created with their required dependencies.
    """
    
    @staticmethod
    def create_storage(config: MemoryConfig) -> FileMemoryStorage:
        """
        Create storage backend based on configuration.
        
        Args:
            config: Memory configuration
            
        Returns:
            Storage backend instance
            
        Raises:
            ValueError: If backend type is not supported
        """
        if config.is_file_backend:
            logger.info(f"[MemoryFactory] Creating FileMemoryStorage at {config.memory_root}")
            return FileMemoryStorage(str(config.memory_root))
        
        elif config.is_neo4j_backend:
            if not all([config.neo4j_uri, config.neo4j_user, config.neo4j_password]):
                raise ValueError("Neo4j backend requires uri, user, and password")
            
            logger.info(f"[MemoryFactory] Creating Neo4jMemoryStorage at {config.neo4j_uri}")
            return Neo4jMemoryStorage(
                uri=config.neo4j_uri,
                user=config.neo4j_user,
                password=config.neo4j_password,
            )
        
        else:
            raise ValueError(f"Unsupported backend type: {config.backend_type}")
    
    @staticmethod
    def create_short_term_memory(config: MemoryConfig) -> SqlShortTermMemory:
        """
        Create short-term memory backend.
        
        Args:
            config: Memory configuration
            
        Returns:
            Short-term memory instance
        """
        logger.info(f"[MemoryFactory] Creating SqlShortTermMemory")
        return SqlShortTermMemory()
    
    @classmethod
    def create_manager(
        cls,
        config: Optional[MemoryConfig] = None,
        storage: Optional[FileMemoryStorage] = None,
        short_term: Optional[SqlShortTermMemory] = None,
    ) -> MemoryManager:
        """
        Create memory manager with all dependencies.
        
        Args:
            config: Memory configuration (creates default if None)
            storage: Storage backend (creates if None)
            short_term: Short-term memory (creates if None)
            
        Returns:
            Configured MemoryManager instance
        """
        config = config or MemoryConfig()
        
        if storage is None:
            storage = cls.create_storage(config)
        
        if short_term is None:
            short_term = cls.create_short_term_memory(config)
        
        logger.info(f"[MemoryFactory] Creating MemoryManager")
        return MemoryManager(
            config=config,
            storage=storage,
            short_term=short_term,
        )
    
    @classmethod
    def create_extractor(
        cls,
        config: MemoryConfig,
        storage: FileMemoryStorage,
    ) -> MemoryExtractionService:
        """
        Create memory extraction service.
        
        Args:
            config: Memory configuration
            storage: Storage backend
            
        Returns:
            MemoryExtractionService instance
        """
        return MemoryExtractionService(
            storage=storage,
            config=config,
        )
    
    @classmethod
    def create_consolidator(
        cls,
        storage: FileMemoryStorage,
    ) -> MemoryConsolidationService:
        """
        Create memory consolidation service.
        
        Args:
            storage: Storage backend
            
        Returns:
            MemoryConsolidationService instance
        """
        return MemoryConsolidationService(storage=storage)
    
    @classmethod
    def create_retriever(
        cls,
        storage: FileMemoryStorage,
    ) -> MemoryRetrievalService:
        """
        Create memory retrieval service.
        
        Args:
            storage: Storage backend
            
        Returns:
            MemoryRetrievalService instance
        """
        return MemoryRetrievalService(storage=storage)
    
    @classmethod
    def create_smart_retriever(
        cls,
        config: MemoryConfig,
        storage: FileMemoryStorage,
    ) -> SmartMemoryRetriever:
        """
        Create smart memory retriever.
        
        Args:
            config: Memory configuration
            storage: Storage backend
            
        Returns:
            SmartMemoryRetriever instance
        """
        return SmartMemoryRetriever(
            storage=storage,
            config=config,
        )
    
    @classmethod
    def create_quality_analyzer(
        cls,
        config: MemoryConfig,
        storage: FileMemoryStorage,
    ) -> MemoryQualityAnalyzer:
        """
        Create quality analyzer.
        
        Args:
            config: Memory configuration
            storage: Storage backend
            
        Returns:
            MemoryQualityAnalyzer instance
        """
        return MemoryQualityAnalyzer(
            storage=storage,
            config=config,
        )
    
    @staticmethod
    def create_state_tracker() -> MemoryStateTracker:
        """
        Create state tracker.
        
        Returns:
            MemoryStateTracker instance
        """
        return MemoryStateTracker()
    
    @classmethod
    def create_daily_log_writer(
        cls,
        config: MemoryConfig,
    ) -> DailyLogWriter:
        """
        Create daily log writer.
        
        Args:
            config: Memory configuration
            
        Returns:
            DailyLogWriter instance
        """
        return DailyLogWriter(root_path=config.memory_root)
    
    @classmethod
    def create_log_consolidator(
        cls,
        config: MemoryConfig,
    ) -> LogConsolidator:
        """
        Create log consolidator.
        
        Args:
            config: Memory configuration
            
        Returns:
            LogConsolidator instance
        """
        return LogConsolidator(root_path=config.memory_root)
    
    @classmethod
    def create_two_tier_manager(
        cls,
        config: MemoryConfig,
        storage: FileMemoryStorage,
    ) -> TwoTierMemoryManager:
        """
        Create two-tier memory manager.
        
        Args:
            config: Memory configuration
            storage: Storage backend
            
        Returns:
            TwoTierMemoryManager instance
        """
        return TwoTierMemoryManager(
            storage=storage,
            config=config,
        )
    
    @classmethod
    def create_auto_extractor(
        cls,
        config: MemoryConfig,
        manager: MemoryManager,
    ) -> AutoMemoryExtractor:
        """
        Create auto memory extractor.
        
        Args:
            config: Memory configuration
            manager: Memory manager instance
            
        Returns:
            AutoMemoryExtractor instance
        """
        return AutoMemoryExtractor(
            memory_manager=manager,
            config=config,
        )
    
    @classmethod
    def create_complete_system(
        cls,
        config: Optional[MemoryConfig] = None,
    ) -> "CompleteMemorySystem":
        """
        Create a complete memory system with all components.
        
        This is a convenience method for quickly setting up the entire
        memory system with sensible defaults.
        
        Args:
            config: Memory configuration (uses default if None)
            
        Returns:
            CompleteMemorySystem with all components
        """
        config = config or MemoryConfig()
        
        storage = cls.create_storage(config)
        short_term = cls.create_short_term_memory(config)
        manager = cls.create_manager(config, storage, short_term)
        
        return CompleteMemorySystem(
            config=config,
            storage=storage,
            short_term=short_term,
            manager=manager,
            factory=cls,
        )


class CompleteMemorySystem:
    """
    Holds all memory system components for easy access.
    
    This is a convenience class that holds references to all
    components created by the factory.
    """
    
    def __init__(
        self,
        config: MemoryConfig,
        storage: FileMemoryStorage,
        short_term: SqlShortTermMemory,
        manager: MemoryManager,
        factory: MemoryFactory,
    ):
        self.config = config
        self.storage = storage
        self.short_term = short_term
        self.manager = manager
        self._factory = factory
        
        # Lazy-loaded components
        self._extraction: Optional[MemoryExtractionService] = None
        self._smart_retriever: Optional[SmartMemoryRetriever] = None
        self._quality: Optional[MemoryQualityAnalyzer] = None
    
    async def initialize(self) -> None:
        """Initialize all components."""
        await self.short_term.initialize()
        await self.manager.initialize()
    
    async def shutdown(self) -> None:
        """Shutdown all components."""
        # Note: We do NOT call flush() here because it deletes all data.
        # flush() is only for testing. This method just releases resources.
        pass
    
    @property
    def extraction(self) -> MemoryExtractionService:
        """Get extraction service (lazy)."""
        if self._extraction is None:
            self._extraction = self._factory.create_extractor(
                self.config, self.storage
            )
        return self._extraction
    
    @property
    def smart_retriever(self) -> SmartMemoryRetriever:
        """Get smart retriever (lazy)."""
        if self._smart_retriever is None:
            self._smart_retriever = self._factory.create_smart_retriever(
                self.config, self.storage
            )
        return self._smart_retriever
    
    @property
    def quality(self) -> MemoryQualityAnalyzer:
        """Get quality analyzer (lazy)."""
        if self._quality is None:
            self._quality = self._factory.create_quality_analyzer(
                self.config, self.storage
            )
        return self._quality
