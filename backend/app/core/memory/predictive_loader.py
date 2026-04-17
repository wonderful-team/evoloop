"""
Predictive Memory Loading
=========================
Background/parallel loading of relevant memories for context injection.
"""

import logging
from typing import Optional

from app.core.memory.retrieval import get_relevant_memories
from app.core.memory.state_tracking import predictive_cache

logger = logging.getLogger(__name__)


async def predictive_memory_load(
    thread_id: str,
    run_id: str,
    project_id: Optional[int] = None,
    human_message: str = "",
) -> None:
    """
    Predictively load relevant memories in the background and cache them.
    
    This speeds up context injection by pre-calculating relevance before
    the main reasoning loop needs the context.
    """
    if not human_message:
        return

    logger.info(f"[PredictiveLoader] Loading memories for thread {thread_id}...")

    try:
        # Perform retrieval
        results = await get_relevant_memories(
            query=human_message,
            project_id=project_id,
            max_results=5
        )
        
        # Store in predictive cache
        predictive_cache.set(thread_id, human_message, results)
        
        logger.info(f"[PredictiveLoader] Successfully cached {len(results)} memories for query: {human_message[:50]}...")
        
    except Exception as e:
        logger.warning(f"[PredictiveLoader] Failed to pre-load memories: {e}")
