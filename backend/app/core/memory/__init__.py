"""
Memory Component Package

Unified memory system for EvoLoop.

This module provides:
- Short-term memory: Conversation history (SQL)
- Long-term memory: Persistent knowledge (File-based, SQLite + LanceDB)
- Smart retrieval: LLM-assisted relevance selection
- Two-tier hot/cold memory architecture
"""

# Services
# Configuration and Dependency Injection
from app.core.memory.config import MemoryConfig
from app.core.memory.container import MemoryContainer

# Maintenance
from app.core.memory.maintenance import (
    MaintenanceScheduler,
    MemoryMaintenanceAgent,
    get_maintenance_status,
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
from app.core.memory.schemas import CheckpointDedupResult
from app.core.memory.state_tracking import (
    MemoryStateTracker,
    filter_unsurfaced_memories,
    get_surfaced_memory_ids,
    mark_memories_surfaced,
    memory_tracker,
    predictive_cache,
)

__all__ = [
    # Manager
    "MemoryManager",
    # Configuration & Dependency Injection
    "MemoryConfig",
    "MemoryContainer",
    # Models
    "MemoryEntry",
    "MemoryIndexEntry",
    "MemorySearchResult",
    "MemoryType",
    "PrivacyLevel",
    # Services
    "MemoryPruningService",
    "MemoryRetriever",
    "get_relevant_memories",
    "MemoryQualityAnalyzer",
    # Types
    "QualityScores",
    "CleanupRecommendation",
    "MemoryStateTracker",
    "memory_tracker",
    "predictive_cache",
    "mark_memories_surfaced",
    "get_surfaced_memory_ids",
    "filter_unsurfaced_memories",
    "CheckpointDedupResult",
    # Maintenance
    "MemoryMaintenanceAgent",
    "MaintenanceScheduler",
    "trigger_maintenance",
    "get_maintenance_status",
]
