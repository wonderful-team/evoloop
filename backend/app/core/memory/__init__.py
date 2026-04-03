"""
Memory Component Package

Unified memory system for EvoLoop.

This module provides:
- Short-term memory: Conversation history (SQL)
- Long-term memory: Persistent knowledge (File or Neo4j)
- Auto-extraction: Automatic memory creation from conversations
- Smart retrieval: LLM-assisted relevance selection

Usage (with dependency injection):
    from app.core.memory import MemoryContainer, MemoryConfig
    from app.core.memory.models import MemoryEntry, MemoryType
    
    async def main():
        config = MemoryConfig.from_settings()
        container = MemoryContainer(config)
        await container.initialize()
        
        manager = container.memory_manager
        
        # Save a memory
        entry = MemoryEntry(
            id="mem_001",
            type=MemoryType.PROJECT,
            title="Architecture Decision",
            content="We decided to use PostgreSQL...",
        )
        await manager.save_memory(entry)
        
        # Search memories
        results = await manager.search_memories("database")
        
        # Extract from conversation
        await manager.extract_memories(thread_id, messages)

Architecture:
    MemoryManager (unified facade)
    ├── Short-term: SqlShortTermMemory (SQLite/PostgreSQL)
    ├── Long-term: FileMemoryStorage | Neo4jMemoryStorage
    ├── Extraction: MemoryExtractionService
    └── Retrieval: MemoryRetrievalService
"""

# Main facade
from app.core.memory.manager import MemoryManager

# New: Configuration and Dependency Injection
from app.core.memory.config import MemoryConfig, default_memory_config
from app.core.memory.container import MemoryContainer, get_container, reset_container
from app.core.memory.factory import MemoryFactory, CompleteMemorySystem

# Data models
from app.core.memory.models import (
    MemoryEntry,
    MemoryIndexEntry,
    MemorySearchResult,
    MemoryType,
    PrivacyLevel,
)

# Legacy models (for backward compatibility)
from app.core.memory.interfaces.long_term import Concept, Episode, SearchResult

# Backends
from app.core.memory.backends.file_backend import FileMemoryStorage

# Services
from app.core.memory.extraction import (
    MemoryExtractionService,
    MemoryConsolidationService,
)
from app.core.memory.retrieval import MemoryRetrievalService
from app.core.memory.smart_retrieval import SmartMemoryRetriever, get_relevant_memories
from app.core.memory.quality import (
    MemoryQualityAnalyzer,
    QualityScores,
    CleanupRecommendation,
)
from app.core.memory.state_tracking import (
    MemoryStateTracker,
    memory_tracker,
    mark_memories_surfaced,
    get_surfaced_memory_ids,
    filter_unsurfaced_memories,
)
from app.core.memory.daily_log import DailyLogWriter, LogConsolidator
from app.core.memory.two_tier import (
    TwoTierMemoryManager,
    MemorySection,
    SectionBudget,
)

__all__ = [
    # Manager
    "MemoryManager",
    
    # Configuration & Dependency Injection (NEW)
    "MemoryConfig",
    "default_memory_config",
    "MemoryContainer",
    "get_container",
    "reset_container",
    "MemoryFactory",
    "CompleteMemorySystem",
    
    # Models
    "MemoryEntry",
    "MemoryIndexEntry",
    "MemorySearchResult",
    "MemoryType",
    "PrivacyLevel",
    
    # Legacy models
    "Concept",
    "Episode",
    "SearchResult",
    
    # Backends
    "FileMemoryStorage",
    
    # Services
    "MemoryExtractionService",
    "MemoryConsolidationService",
    "MemoryRetrievalService",
    "SmartMemoryRetriever",
    "get_relevant_memories",
    "MemoryQualityAnalyzer",
    
    # Types
    "QualityScores",
    "CleanupRecommendation",
    "MemoryStateTracker",
    "memory_tracker",
    "mark_memories_surfaced",
    "get_surfaced_memory_ids",
    "filter_unsurfaced_memories",
    "DailyLogWriter",
    "LogConsolidator",
    "TwoTierMemoryManager",
    "MemorySection",
    "SectionBudget",
]
