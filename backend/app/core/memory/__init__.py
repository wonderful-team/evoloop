"""
Memory Component Package

Unified memory system for EvoLoop.

This module provides:
- Short-term memory: Conversation history (SQL)
- Long-term memory: Persistent knowledge (File or Neo4j)
- Auto-extraction: Automatic memory creation from conversations
- Smart retrieval: LLM-assisted relevance selection

Usage:
    from app.core.memory import memory_manager
    from app.core.memory.models import MemoryEntry, MemoryType
    
    # Save a memory
    entry = MemoryEntry(
        id="mem_001",
        type=MemoryType.PROJECT,
        title="Architecture Decision",
        content="We decided to use PostgreSQL...",
    )
    await memory_manager.save_memory(entry)
    
    # Search memories
    results = await memory_manager.search_memories("database")
    
    # Extract from conversation
    await memory_manager.extract_memories(thread_id, messages)

Architecture:
    MemoryManager (unified facade)
    ├── Short-term: SqlShortTermMemory (SQLite/PostgreSQL)
    ├── Long-term: FileMemoryStorage | Neo4jMemoryStorage
    ├── Extraction: MemoryExtractionService
    └── Retrieval: MemoryRetrievalService
"""

# Main facade
from app.core.memory.manager import MemoryManager, memory_manager

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

__all__ = [
    # Manager
    "MemoryManager",
    "memory_manager",
    
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
]
