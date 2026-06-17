"""
Memory System Configuration

Centralized configuration for the memory system to avoid scattered settings access.
All memory-related settings are encapsulated in the MemoryConfig dataclass.

支持两级存储：
- 用户级 (user_memory_root): ~/.evoloop/memory/ - 偏好、经验教训、通用领域术语
- 项目级 (project_memory_root): {project}/.evoloop/memory/ - 项目上下文、决策、架构
"""

import logging
from pathlib import Path

from pydantic import Field

from app.core.config import settings
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


def _default_user_memory_root() -> Path:
    """Resolve user-level memory root from EVOLOOP_APP_DATA_DIR."""
    return Path(settings.APP_DATA_DIR) / "memory"


def get_project_memory_root(project_path: str) -> Path:
    """
    Get project-level memory root.
    
    Args:
        project_path: 项目本地路径
        
    Returns:
        Path 指向 {project}/.evoloop/memory/
    """
    from app.core.project.utils import get_memory_path
    return get_memory_path(project_path)


class MemoryConfig(DynamicBaseModel):
    """
    Centralized configuration for the memory system.
    
    支持两级存储架构：
    - user_memory_root: 用户级记忆（偏好、经验教训、通用术语）
    - project_memory_root: 项目级记忆（上下文、决策、架构）
    
    Usage:
        config = MemoryConfig.from_settings()
        
        # 用户级操作
        user_storage = MemoryStore(str(config.user_memory_root))
        
        # 项目级操作
        project_root = config.get_project_memory_root("/path/to/project")
        project_storage = MemoryStore(str(project_root))
    """

    # Storage settings
    user_memory_root: Path = Field(default_factory=_default_user_memory_root)
    """Root directory for user-level memory storage (preferences, lessons, domain terms)."""

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
        """Create configuration from application settings."""
        from app.core.config import settings

        return cls(
            user_memory_root=Path(getattr(settings, 'BRAIN_MEMORY_ROOT', _default_user_memory_root())),
            extraction_interval=getattr(settings, 'AUTO_MEMORY_EXTRACTION_INTERVAL', 1),
            min_messages_for_extraction=getattr(settings, 'MIN_MESSAGES_FOR_EXTRACTION', 4),
            max_extraction_turns=getattr(settings, 'MAX_EXTRACTION_TURNS', 5),
            default_search_limit=getattr(settings, 'MEMORY_SEARCH_LIMIT', 10),
            max_selections=getattr(settings, 'MAX_MEMORY_SELECTIONS', 5),
            min_relevance_score=getattr(settings, 'MEMORY_MIN_RELEVANCE', 0.7),
            quality_check_enabled=getattr(settings, 'MEMORY_QUALITY_CHECK', True),
            auto_cleanup_enabled=getattr(settings, 'MEMORY_AUTO_CLEANUP', False),
            hot_memory_max_chars=getattr(settings, 'HOT_MEMORY_MAX_CHARS', 8000),
            cold_memory_results=getattr(settings, 'COLD_MEMORY_RESULTS', 5),
            pruning_threshold=getattr(settings, 'MEMORY_PRUNE_THRESHOLD', 100),
            context_window_size=getattr(settings, 'CONTEXT_WINDOW_SIZE', 20),
            log_level=getattr(settings, 'MEMORY_LOG_LEVEL', 'INFO'),
        )

    @staticmethod
    def get_project_memory_root(project_path: str) -> Path:
        """Get project-level memory root path."""
        return get_project_memory_root(project_path)

    @property
    def extraction_enabled(self) -> bool:
        """Check if auto-extraction is enabled."""
        return self.extraction_interval > 0


# Default configuration instance (for backward compatibility)
# Lazily resolved so that module-level import does not bypass settings.
default_memory_config: MemoryConfig | None = None


def get_default_memory_config() -> MemoryConfig:
    """Get the lazily-initialized default memory config."""
    global default_memory_config
    if default_memory_config is None:
        default_memory_config = MemoryConfig.from_settings()
    return default_memory_config
