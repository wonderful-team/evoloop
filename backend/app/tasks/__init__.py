"""
Celery tasks for EvoLoop.

This module contains background tasks for:
- Memory consolidation
- Quality analysis
- Codebase indexing
- Project synchronization
"""

from app.tasks.memory_tasks import (
    nightly_consolidation,
    analyze_memory_quality,
    cleanup_stale_memories,
    generate_daily_memory_report,
    regenerate_hot_memory,
    MEMORY_BEAT_SCHEDULE,
)

__all__ = [
    "nightly_consolidation",
    "analyze_memory_quality",
    "cleanup_stale_memories",
    "generate_daily_memory_report",
    "regenerate_hot_memory",
    "MEMORY_BEAT_SCHEDULE",
]
