"""
Deep Dream — offline memory distillation system.

During idle periods, the agent "dreams": it replays recent episodes
(successful task executions), distills reusable insights (patterns,
gotchas, architectural decisions), and promotes them to strategic
CONCEPT entries in long-term memory.

Unlike MemoryConsolidator (which merges/deduplicates existing memories),
Deep Dream is ADDITIVE — it creates new knowledge from raw experience
without deleting the source episodes.

Architecture:
    EpisodeReplay  →  DeepDreamDistiller  →  MemoryManager.save()
    (load episodes)    (LLM distillation)      (store insights)

    DreamScheduler orchestrates the cycle (cron + idle trigger).
"""

from .distiller import DeepDreamDistiller
from .replay import EpisodeReplay
from .scheduler import DreamScheduler
from .schemas import DreamInsight, DreamRecord, DreamResult

__all__ = [
    "DreamRecord",
    "DreamInsight",
    "DreamResult",
    "EpisodeReplay",
    "DeepDreamDistiller",
    "DreamScheduler",
]
