import asyncio
import logging
from typing import List, Optional

from celery import shared_task

from app.core.memory import memory_manager
from app.core.memory.interfaces.long_term import Concept as MemConcept
from app.core.learning.trace_recorder import sync_thread_to_graph

logger = logging.getLogger(__name__)

@shared_task(name="engine_harvest_concepts")
def harvest_concepts_task(concepts_data: List[dict], project_id: int):
    """
    Background task to store harvested concepts in Neo4j.
    concepts_data: List of dicts with 'name' and 'description'.
    """
    if not concepts_data:
        return

    async def _run():
        logger.info(f"[Celery] Harvesting {len(concepts_data)} concepts...")
        for c in concepts_data:
            try:
                mem_concept = MemConcept(c["name"], c["description"], project_id, [])
                await memory_manager.long_term.store_concept(mem_concept)
                logger.info(f"Harvested concept: {c['name']}")
            except Exception as e:
                logger.warning(f"Failed to store concept {c['name']}: {e}")

    asyncio.run(_run())

@shared_task(name="engine_record_episode")
def record_episode_task(
    thread_id: str,
    project_id: int,
    goal: Optional[str] = None,
    result_summary: Optional[str] = None,
    concept_names: Optional[List[str]] = None,
    source_message_id: Optional[str] = None,
):
    """
    Background task to sync thread trace to Neo4j Episode graph.
    """
    logger.info(f"[Celery] Recording episode for thread {thread_id} (Source: {source_message_id})...")

    async def _run():
        try:
            await sync_thread_to_graph(
                thread_id=thread_id,
                project_id=project_id,
                goal=goal,
                result_summary=result_summary,
                concept_names=concept_names,
                source_message_id=source_message_id,
            )
            logger.info(f"[Celery] Episode recorded for thread {thread_id}")
        except Exception as e:
            logger.error(f"[Celery] Failed to record episode: {e}")

    asyncio.run(_run())
