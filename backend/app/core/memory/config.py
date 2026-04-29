"""
Memory System Configuration

Centralized configuration for the memory system to avoid scattered settings access.
All memory-related settings are encapsulated in the MemoryConfig dataclass.
"""

import logging
from pathlib import Path

from pydantic import Field

from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class MemoryConfig(DynamicBaseModel):
    """
    Centralized configuration for the memory system.
    
    This replaces scattered settings access throughout the memory module,
    making dependencies explicit and the system more testable.
    
    Usage:
        # Production
        config = MemoryConfig.from_settings()
        
        # Testing
        config = MemoryConfig(
            memory_root=Path("/tmp/test_memory"),
            backend_type="file",
            extraction_interval=1,
        )
    """

    # Storage settings
    memory_root: Path = Field(default_factory=lambda: Path.home() / ".evoloop" / "memory")
    """Root directory for file-based memory storage."""

    backend_type: str = "file"
    """Backend type: 'file' or 'neo4j'."""

    # Neo4j settings (for full mode)
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None

    # Short-term memory settings
    short_term_backend: str = "sqlite"
    """Short-term backend: 'sqlite' or 'postgresql'."""

    database_url: str | None = None
    """Database URL for PostgreSQL mode."""

    # Extraction settings
    extraction_interval: int = 1
    """Extract memories every N conversations (0 to disable)."""

    min_messages_for_extraction: int = 4
    """Minimum messages required to trigger extraction."""

    max_extraction_turns: int = 5
    """Maximum turns for extraction agent."""

    # Retrieval settings
    default_search_limit: int = 10
    """Default number of results to return from search."""

    max_selections: int = 5
    """Maximum number of memories to select via LLM ranking."""

    min_relevance_score: float = 0.7
    """Minimum relevance score for search results."""

    # Quality settings
    quality_check_enabled: bool = True
    """Enable automatic quality analysis."""

    auto_cleanup_enabled: bool = False
    """Enable automatic cleanup of low-quality memories."""

    # Two-tier settings
    hot_memory_max_chars: int = 8000
    """Maximum characters for hot (tier-1) memory."""

    cold_memory_results: int = 5
    """Number of cold memory results to retrieve."""

    # Pruning settings
    pruning_threshold: int = 100
    """Number of messages before pruning is considered."""

    context_window_size: int = 20
    """Number of recent messages to keep in context."""

    # Logging
    log_level: str = "INFO"
    """Logging level for memory system."""

    @classmethod
    def from_settings(cls) -> "MemoryConfig":
        """
        Create configuration from Django/Celery settings.
        
        This is the production entry point. For testing, create
        MemoryConfig instances directly with test values.
        """
        from app.core.config import settings

        return cls(
            memory_root=Path(getattr(settings, 'BRAIN_MEMORY_ROOT',
                                     Path.home() / ".evoloop" / "memory")),
            backend_type=getattr(settings, 'MEMORY_BACKEND', 'file'),
            neo4j_uri=getattr(settings, 'NEO4J_URI', None),
            neo4j_user=getattr(settings, 'NEO4J_USER', None),
            neo4j_password=getattr(settings, 'NEO4J_PASSWORD', None),
            short_term_backend=getattr(settings, 'SHORT_TERM_BACKEND', 'sqlite'),
            database_url=getattr(settings, 'DATABASE_URL', None),
            extraction_interval=getattr(settings, 'AUTO_MEMORY_EXTRACTION_INTERVAL', 1),
            min_messages_for_extraction=getattr(settings, 'MIN_MESSAGES_FOR_EXTRACTION', 4),
            max_extraction_turns=getattr(settings, 'MAX_EXTRACTION_TURNS', 5),
            default_search_limit=getattr(settings, 'MEMORY_SEARCH_LIMIT', 10),
            min_relevance_score=getattr(settings, 'MEMORY_MIN_RELEVANCE', 0.7),
            quality_check_enabled=getattr(settings, 'MEMORY_QUALITY_CHECK', True),
            auto_cleanup_enabled=getattr(settings, 'MEMORY_AUTO_CLEANUP', False),
            hot_memory_max_chars=getattr(settings, 'HOT_MEMORY_MAX_CHARS', 8000),
            cold_memory_results=getattr(settings, 'COLD_MEMORY_RESULTS', 5),
            pruning_threshold=getattr(settings, 'MEMORY_PRUNE_THRESHOLD', 100),
            context_window_size=getattr(settings, 'CONTEXT_WINDOW_SIZE', 20),
            log_level=getattr(settings, 'MEMORY_LOG_LEVEL', 'INFO'),
        )

    def to_dict(self) -> dict:
        """Convert configuration to dictionary (legacy support)."""
        return self.model_dump()

    @property
    def is_file_backend(self) -> bool:
        """Check if using file-based backend."""
        return self.backend_type == "file"

    @property
    def is_neo4j_backend(self) -> bool:
        """Check if using Neo4j backend."""
        return self.backend_type == "neo4j"

    @property
    def extraction_enabled(self) -> bool:
        """Check if auto-extraction is enabled."""
        return self.extraction_interval > 0


# Default configuration instance (for backward compatibility)
default_memory_config = MemoryConfig()
