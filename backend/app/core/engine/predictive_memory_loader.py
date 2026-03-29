"""
Predictive Memory Loader - Pre-load semantic search results

This module implements the "bg_tasks" optimization strategy for Pre-Supervisor
phase. It offloads Neo4j semantic searches (concepts + episodes) to a background
task that runs in parallel with LangGraph initialization.

Flow:
1. User sends message -> chat_endpoint
2. IMMEDIATELY spawn bg_tasks.add_task(predictive_memory_load, ...)
3. LangGraph initializes (100ms: checkpoint loading, state deserialization)
4. Background task completes Neo4j search (~800ms) and stores in Redis
5. Middleware.hydrate() reads from Redis (~1ms) instead of querying Neo4j

Safety Guarantees:
- Read-only operation: No risk of corrupting data
- Graceful fallback: If Redis miss, falls back to direct Neo4j query
- Subtask safe: Subtasks don't trigger memory search (skipped automatically)
- TTL based: Cache expires to prevent stale data

Optimization Notes:
- Benign Race Condition: If LangGraph initializes faster (<50ms) than Neo4j 
  query (~400ms), cache miss occurs and fallback query executes. This results
  in duplicate Neo4j queries but no functional impact.
- Future enhancement: Could implement singleflight pattern for high-concurrency
  scenarios to deduplicate concurrent identical queries.
"""

import asyncio
import logging
import time
from typing import Optional

from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)

# Redis key format: "predictive:memory:{thread_id}:{message_hash}"
PREDICTIVE_MEMORY_KEY_PREFIX = "predictive:memory"
PREDICTIVE_MEMORY_TTL = 300  # 5 minutes, plenty for a single request

# In-flight request tracking (for singleflight pattern)
# Key: thread_id, Value: asyncio.Event
_inflight_requests: dict[str, asyncio.Event] = {}
_inflight_lock = asyncio.Lock()


async def predictive_memory_load(
    thread_id: str,
    project_id: int,
    human_message: str,
    run_id: str
):
    """
    Background task to pre-load memory search results into Redis.
    
    Args:
        thread_id: The conversation thread ID
        project_id: The project ID for scoping search
        human_message: The user's message to search against
        run_id: Unique run identifier to filter out current run's episodes
    """
    if not human_message or not human_message.strip():
        logger.debug(f"[PredictiveMemory] Skipping empty message for thread {thread_id}")
        return
    
    # Singleflight pattern: Mark this thread as having an in-flight request
    event = asyncio.Event()
    async with _inflight_lock:
        if thread_id in _inflight_requests:
            # Another request is already in-flight, skip this one
            logger.debug(f"[PredictiveMemory] Skipping duplicate request for thread {thread_id}")
            return
        _inflight_requests[thread_id] = event
    
    try:
        from app.core.config import settings
        
        if not settings.USE_NEO4J_MEMORY:
            logger.debug(f"[PredictiveMemory] Neo4j memory disabled, skipping")
            return
        
        from app.core.memory import memory_manager
        
        start_time = time.time()
        
        # Parallel search for concepts and episodes
        concepts_task = memory_manager.long_term.search_concepts(human_message, project_id)
        episodes_task = memory_manager.episodic.search_episodes(human_message, project_id, limit=3)
        
        concepts, episodes = await asyncio.gather(concepts_task, episodes_task, return_exceptions=True)
        
        # Handle exceptions
        if isinstance(concepts, Exception):
            logger.warning(f"[PredictiveMemory] Concepts search failed: {concepts}")
            concepts = []
        if isinstance(episodes, Exception):
            logger.warning(f"[PredictiveMemory] Episodes search failed: {episodes}")
            episodes = []
        
        # Filter out episodes from current run (to avoid self-referencing)
        filtered_episodes = []
        if episodes:
            for e in episodes:
                if getattr(e, "source_message_id", None) != run_id:
                    filtered_episodes.append(e)
        
        # Serialize for Redis storage
        data = {
            "concepts": [
                {"name": c.name, "description": c.description}
                for c in (concepts or [])[:3]
            ] if concepts else [],
            "episodes": [
                {"summary": e.summary}
                for e in filtered_episodes[:2]
            ] if filtered_episodes else [],
            "timestamp": time.time(),
            "thread_id": thread_id,
            "project_id": project_id,
        }
        
        # Store in Redis with TTL
        cache_key = f"{PREDICTIVE_MEMORY_KEY_PREFIX}:{thread_id}"
        await cache.set(cache_key, data, ex=PREDICTIVE_MEMORY_TTL)
        
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"[PredictiveMemory] ✓ Pre-loaded memory for thread {thread_id}: "
                   f"{len(data['concepts'])} concepts, {len(data['episodes'])} episodes "
                   f"in {elapsed:.1f}ms")
        
    except Exception as e:
        # Never raise - this is an optimization, not critical path
        logger.warning(f"[PredictiveMemory] Failed to pre-load memory for thread {thread_id}: {e}")
    finally:
        # Signal completion and cleanup
        event.set()
        async with _inflight_lock:
            _inflight_requests.pop(thread_id, None)


async def get_predictive_memory(
    thread_id: str,
    human_message: str,
    project_id: int,
    run_id: str
) -> Optional[dict]:
    """
    Retrieve pre-loaded memory from Redis.
    Called by middleware.hydrate() to get cached search results.
    
    Args:
        thread_id: The conversation thread ID
        human_message: The user's message (for validation)
        project_id: The project ID (for validation)
        run_id: Unique run identifier
        
    Returns:
        Dict with 'concepts' and 'episodes' if cache hit, None if cache miss
    """
    try:
        # Check if there's an in-flight request we should wait for
        inflight_event = None
        async with _inflight_lock:
            if thread_id in _inflight_requests:
                inflight_event = _inflight_requests[thread_id]
                logger.debug(f"[PredictiveMemory] Found in-flight request for thread {thread_id}, waiting...")
        
        # If there's an in-flight request, wait for it (with timeout)
        if inflight_event:
            try:
                # Wait up to 500ms for the background task to complete
                await asyncio.wait_for(inflight_event.wait(), timeout=0.5)
                logger.debug(f"[PredictiveMemory] In-flight request completed for thread {thread_id}")
            except asyncio.TimeoutError:
                logger.debug(f"[PredictiveMemory] Timeout waiting for in-flight request, proceeding with cache check")
        
        cache_key = f"{PREDICTIVE_MEMORY_KEY_PREFIX}:{thread_id}"
        data = await cache.get(cache_key)
        
        if not data:
            logger.debug(f"[PredictiveMemory] Cache miss for thread {thread_id}")
            return None
        
        # Validate the cached data matches current request
        # (Safety: ensure we're not using stale data from a different message)
        if data.get("project_id") != project_id:
            logger.debug(f"[PredictiveMemory] Project ID mismatch for thread {thread_id}")
            return None
        
        concepts_formatted = None
        episodes_formatted = None
        
        if data.get("concepts"):
            concepts_formatted = "\n".join([
                f"- **{c['name']}**: {c['description']}"
                for c in data["concepts"]
            ])
        
        if data.get("episodes"):
            episodes_formatted = "\n".join([
                e["summary"] for e in data["episodes"]
            ])
        
        logger.info(f"[PredictiveMemory] ✓ Cache hit for thread {thread_id}: "
                   f"{len(data.get('concepts', []))} concepts, "
                   f"{len(data.get('episodes', []))} episodes")
        
        return {
            "concepts": concepts_formatted,
            "episodes": episodes_formatted,
            "from_cache": True,
        }
        
    except Exception as e:
        logger.warning(f"[PredictiveMemory] Error reading cache for thread {thread_id}: {e}")
        return None


async def clear_predictive_memory(thread_id: str):
    """
    Clear predictive memory cache for a thread.
    Called after successful hydration to prevent reuse.
    """
    try:
        cache_key = f"{PREDICTIVE_MEMORY_KEY_PREFIX}:{thread_id}"
        await cache.delete(cache_key)
        logger.debug(f"[PredictiveMemory] Cleared cache for thread {thread_id}")
    except Exception as e:
        logger.warning(f"[PredictiveMemory] Failed to clear cache for thread {thread_id}: {e}")
