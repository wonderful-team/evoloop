"""
Checkpoint Pruner - Utilities for cleaning up historical state to prevent bloat.
Designed to work with LangGraph's AsyncSqliteSaver schema.
"""

import logging

import aiosqlite

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    """Resolve the SQLite database path from the LangGraph checkpointer config."""
    try:
        from app.core.persistence import get_checkpointer
        cp = get_checkpointer()
        # AsyncSqliteSaver stores path in .conn or .db attrs depending on version
        if hasattr(cp, "conn") and isinstance(cp.conn, str):
            return cp.conn
        if hasattr(cp, "db"):
            return cp.db
    except Exception:
        pass
    # Fallback to default EvoLoop path
    import os
    return os.path.expanduser("~/.evoloop/backend.db")


async def prune_checkpoints(
    max_versions_per_thread: int = 10,
    keep_days: int = 7,
    thread_id: str | None = None
):
    """
    Prune old checkpoints and blobs to save space.
    
    Strategy:
    1. For each thread, find the newest N checkpoint_ids.
    2. Delete all other checkpoints for that thread.
    3. Cleanup orphaned blobs that are no longer referenced.
    """
    db_path = _get_db_path()
    logger.info(f"🚀 Starting checkpoint pruning (max_versions={max_versions_per_thread}, db={db_path}, thread={thread_id})...")

    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = OFF")

            # Find threads to process
            if thread_id:
                threads = [thread_id]
            else:
                async with conn.execute("SELECT DISTINCT thread_id FROM checkpoints") as cur:
                    rows = await cur.fetchall()
                threads = [row[0] for row in rows]

            total_pruned = 0
            for tid in threads:
                async with conn.execute(
                    "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id DESC",
                    (tid,)
                ) as cur:
                    all_ids = [row[0] for row in await cur.fetchall()]

                if len(all_ids) <= max_versions_per_thread:
                    continue

                ids_to_delete = all_ids[max_versions_per_thread:]
                placeholders = ",".join("?" * len(ids_to_delete))

                await conn.execute(
                    f"DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_id IN ({placeholders})",
                    [tid] + ids_to_delete
                )
                await conn.execute(
                    f"DELETE FROM writes WHERE thread_id = ? AND checkpoint_id IN ({placeholders})",
                    [tid] + ids_to_delete
                )
                total_pruned += len(ids_to_delete)

            # Cleanup orphaned blobs
            await conn.execute("""
                DELETE FROM checkpoint_blobs 
                WHERE version NOT IN (SELECT checkpoint_id FROM checkpoints)
            """)

            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.commit()

            logger.info(f"✅ Pruning complete. Removed {total_pruned} old checkpoints.")

    except Exception as e:
        logger.error(f"❌ Checkpoint pruning failed: {e}")


async def auto_prune_on_completion(thread_id: str):
    """Convenience wrapper called from FinishNode when a session ends."""
    await prune_checkpoints(max_versions_per_thread=20, thread_id=thread_id)
