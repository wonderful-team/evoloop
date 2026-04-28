"""
Checkpoint Pruner - Utilities for cleaning up historical state to prevent bloat.
Designed to work with LangGraph's AsyncSqliteSaver schema.
"""

import logging

from app.core.config import settings
from app.infrastructure.database.resource_manager import db_resource_manager

logger = logging.getLogger(__name__)


async def prune_checkpoints(
    max_versions_per_thread: int = 10,
    thread_id: str | None = None
):
    """
    Prune old checkpoints and writes to save space.
    Works with LangGraph AsyncSqliteSaver schema (checkpoints + writes tables).
    """
    logger.info(f"🚀 Starting checkpoint pruning (thread={thread_id})...")

    async with db_resource_manager.get_checkpoint_raw_connection() as conn:
        try:
            placeholder = db_resource_manager.placeholder
            writes_table = db_resource_manager.writes_table

            # 1. Disable constraints
            if settings.EMBEDDED_MODE:
                await conn.execute("PRAGMA foreign_keys = OFF")

            # 2. Find threads to process
            if thread_id:
                threads = [thread_id]
            else:
                query = "SELECT DISTINCT thread_id FROM checkpoints"
                if not settings.EMBEDDED_MODE:
                    async with conn.cursor() as cur:
                        await cur.execute(query)
                        threads = [row[0] for row in await cur.fetchall()]
                else:
                    async with conn.execute(query) as cur:
                        threads = [row[0] for row in await cur.fetchall()]

            total_pruned = 0
            for tid in threads:
                select_query = f"SELECT checkpoint_id FROM checkpoints WHERE thread_id = {placeholder} ORDER BY checkpoint_id DESC"
                
                if not settings.EMBEDDED_MODE:
                    async with conn.cursor() as cur:
                        await cur.execute(select_query, (tid,))
                        all_ids = [row[0] for row in await cur.fetchall()]
                else:
                    async with conn.execute(select_query, (tid,)) as cur:
                        all_ids = [row[0] for row in await cur.fetchall()]

                if len(all_ids) <= max_versions_per_thread:
                    continue

                ids_to_delete = all_ids[max_versions_per_thread:]
                placeholders = ",".join(placeholder for _ in ids_to_delete)

                del_cp_query = f"DELETE FROM checkpoints WHERE thread_id = {placeholder} AND checkpoint_id IN ({placeholders})"
                del_writes_query = f"DELETE FROM {writes_table} WHERE thread_id = {placeholder} AND checkpoint_id IN ({placeholders})"
                
                params = [tid] + ids_to_delete
                
                if not settings.EMBEDDED_MODE:
                    async with conn.cursor() as cur:
                        await cur.execute(del_cp_query, params)
                        await cur.execute(del_writes_query, params)
                else:
                    await conn.execute(del_cp_query, params)
                    await conn.execute(del_writes_query, params)
                
                total_pruned += len(ids_to_delete)

            # 3. Finalize
            if settings.EMBEDDED_MODE:
                await conn.execute("PRAGMA foreign_keys = ON")
                await conn.commit()
            else:
                blob_del_query = """
                    DELETE FROM checkpoint_blobs 
                    WHERE version NOT IN (SELECT checkpoint_id FROM checkpoints)
                """
                async with conn.cursor() as cur:
                    await cur.execute(blob_del_query)

            logger.info(f"✅ Pruning complete. Removed {total_pruned} old checkpoints.")

        except Exception as e:
            logger.exception(f"❌ Checkpoint pruning failed: {e}")
            raise


async def auto_prune_on_completion(thread_id: str):
    """Convenience wrapper called from FinishNode when a session ends."""
    await prune_checkpoints(max_versions_per_thread=20, thread_id=thread_id)
