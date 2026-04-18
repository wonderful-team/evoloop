"""
Memory Component Package

Unified memory system for EvoLoop.

This module provides:
- Short-term memory: Conversation history (SQL)
- Long-term memory: Persistent knowledge (File or Neo4j)
- Auto-extraction: Automatic memory creation from conversations
- Smart retrieval: LLM-assisted relevance selection
"""

# Services
from app.core.memory.auto_extraction import AutoMemoryExtractor
# Backends
from app.core.memory.backends.file_backend import FileMemoryStorage
# Configuration and Dependency Injection
from app.core.memory.config import MemoryConfig, default_memory_config
from app.core.memory.container import MemoryContainer
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
from app.core.memory.pruning import MemoryPruningService
from app.core.memory.quality import (
    CleanupRecommendation,
    MemoryQualityAnalyzer,
    QualityScores,
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

    # Configuration & Dependency Injection
    "MemoryConfig",
    "default_memory_config",
    "MemoryContainer",

    # Models
    "MemoryEntry",
    "MemoryIndexEntry",
    "MemorySearchResult",
    "MemoryType",
    "PrivacyLevel",

    # Backends
    "FileMemoryStorage",

    # Services
    "AutoMemoryExtractor",
    "MemoryPruningService",
    "MemoryRetriever",
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
    "TwoTierMemoryManager",
    "MemorySection",
    "SectionBudget",

    # Maintenance
    "MemoryMaintenanceAgent",
    "MaintenanceScheduler",
    "scheduled_memory_maintenance",
    "trigger_maintenance",
    "get_maintenance_status",
]
