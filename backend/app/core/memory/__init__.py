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
    └── Retrieval: MemoryRetriever
"""

# Backends
from app.core.memory.backends.file_backend import FileMemoryStorage
from . import events

# New: Configuration and Dependency Injection
from app.core.memory.config import MemoryConfig, default_memory_config
from app.core.memory.container import MemoryContainer, get_container, reset_container
from app.core.memory.daily_log import DailyLogWriter, LogConsolidator

# Services
from app.core.memory.extraction import (
    MemoryConsolidationService,
    MemoryExtractionService,
)
from app.core.memory.factory import CompleteMemorySystem, MemoryFactory

# Legacy models (for backward compatibility)
from app.core.memory.interfaces.long_term import Concept, Episode, SearchResult

# Maintenance
from app.core.memory.maintenance import (
    MaintenanceScheduler,
    MemoryMaintenanceAgent,
    get_maintenance_status,
    scheduled_memory_maintenance,
    trigger_maintenance,
)

# Main facade
from app.core.memory.manager import MemoryManager

# Data models
from app.core.memory.models import (
    MemoryEntry,
    MemoryIndexEntry,
    MemorySearchResult,
    MemoryType,
    PrivacyLevel,
)
from app.core.memory.predictive_loader import (
    clear_predictive_memory,
    get_predictive_memory,
    predictive_memory_load,
)
from app.core.memory.quality import (
    CleanupRecommendation,
    MemoryQualityAnalyzer,
    QualityScores,
    quality_analyzer,
)
from app.core.memory.retrieval import MemoryRetriever, get_relevant_memories
from app.core.memory.state_tracking import (
    MemoryStateTracker,
    filter_unsurfaced_memories,
    get_surfaced_memory_ids,
    mark_memories_surfaced,
    memory_tracker,
)
from app.core.memory.two_tier import (
    MemorySection,
    SectionBudget,
    TwoTierMemoryManager,
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
    "MemoryRetriever",
    "get_relevant_memories",
    "MemoryQualityAnalyzer",
    "quality_analyzer",

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

    # Maintenance
    "MemoryMaintenanceAgent",
    "MaintenanceScheduler",
    "scheduled_memory_maintenance",
    "trigger_maintenance",
    "get_maintenance_status",

    # Predictive loader
    "predictive_memory_load",
    "get_predictive_memory",
    "clear_predictive_memory",
]
