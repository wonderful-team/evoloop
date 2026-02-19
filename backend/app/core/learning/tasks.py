"""
Learning system background tasks.

Celery tasks for maintaining learning subsystem health,
including skill embedding generation and maintenance.
"""

import asyncio
import logging

from celery import shared_task

from app.core.learning.discovery import skill_discovery

logger = logging.getLogger(__name__)


@shared_task(name="learning_embed_skills")
def embed_skills(batch_size: int = 50) -> dict:
    """
    Background task to generate embeddings for skills that don't have them.
    
    This should be scheduled to run periodically (e.g., every 5 minutes)
    to ensure newly created skills are searchable via semantic similarity.
    
    Args:
        batch_size: Maximum number of skills to process in this run
        
    Returns:
        Dict with task results
    """
    logger.info(f"[Celery] Starting skill embedding task (batch_size={batch_size})...")
    
    async def _run():
        return await skill_discovery.ensure_skill_embeddings(batch_size)
    
    try:
        updated_count = asyncio.run(_run())
        result = {
            "status": "success",
            "updated_count": updated_count,
        }
        logger.info(f"[Celery] Skill embedding task finished. Updated: {updated_count}")
        return result
    except Exception as e:
        logger.error(f"[Celery] Skill embedding task failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }


@shared_task(name="learning_refresh_all_embeddings")
def refresh_all_skill_embeddings() -> dict:
    """
    Force regeneration of all skill embeddings.
    
    This is useful when the embedding model changes or
    when skill descriptions are bulk-updated.
    
    WARNING: This can be expensive for large skill libraries.
    """
    logger.info("[Celery] Starting full skill embedding refresh...")
    
    async def _run():
        from app.infrastructure.database.sql.database import session_scope
        from app.models.learning import LearnedSkill
        from sqlalchemy import select, update
        
        # First, clear all existing embeddings
        async with session_scope() as db:
            stmt = update(LearnedSkill).where(
                LearnedSkill.is_active == True
            ).values(embedding=None)
            await db.execute(stmt)
            await db.commit()
        
        # Then regenerate in batches
        total_updated = 0
        while True:
            updated = await skill_discovery.ensure_skill_embeddings(batch_size=100)
            total_updated += updated
            if updated == 0:
                break
        
        return total_updated
    
    try:
        total = asyncio.run(_run())
        result = {
            "status": "success",
            "total_updated": total,
        }
        logger.info(f"[Celery] Full embedding refresh finished. Total updated: {total}")
        return result
    except Exception as e:
        logger.error(f"[Celery] Full embedding refresh failed: {e}")
        return {
            "status": "error",
            "error": str(e),
        }
