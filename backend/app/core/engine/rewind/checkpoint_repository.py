"""
Checkpoint repository — abstracts SQLite vs PostgreSQL dialect differences.
"""

import json
import logging

from app.core.config import settings
from app.infrastructure.database.resource_manager import db_resource_manager

logger = logging.getLogger(__name__)


class CheckpointRepository:
    """Low-level checkpoint CRUD with DB-dialect abstraction."""

    @staticmethod
    async def find_checkpoints_ordered_by_step(thread_id: str):
        """Fetch checkpoints ordered by step descending. Returns list of (checkpoint_id, metadata) tuples."""
        async with db_resource_manager.get_raw_connection() as conn:
            if settings.EMBEDDED_MODE:
                query = (
                    f"SELECT checkpoint_id, metadata FROM checkpoints "
                    f"WHERE thread_id = {db_resource_manager.placeholder} "
                    f"ORDER BY CAST(json_extract(metadata, '$.step') AS INTEGER) DESC"
                )
                async with conn.execute(query, (thread_id,)) as cur:
                    return await cur.fetchall()
            else:
                query = (
                    f"SELECT checkpoint_id, metadata FROM checkpoints "
                    f"WHERE thread_id = {db_resource_manager.placeholder} "
                    f"ORDER BY (metadata->>'step')::int DESC"
                )
                async with conn.cursor() as cur:
                    await cur.execute(query, (thread_id,))
                    return await cur.fetchall()

    @staticmethod
    def parse_metadata(raw_meta):
        """Normalize checkpoint metadata to a dict."""
        if raw_meta is None:
            return {}
        if isinstance(raw_meta, str):
            return json.loads(raw_meta)
        if isinstance(raw_meta, bytes):
            return json.loads(raw_meta.decode('utf-8'))
        if isinstance(raw_meta, dict):
            return raw_meta
        return {}

    @staticmethod
    async def delete_checkpoints_and_writes(thread_id: str, checkpoint_ids: list[str]) -> tuple[int, int]:
        """Delete checkpoints and associated writes. Returns (deleted_checkpoints, deleted_writes)."""
        if not checkpoint_ids:
            return 0, 0

        async with db_resource_manager.get_raw_connection() as conn:
            writes_table = db_resource_manager.writes_table
            placeholder = db_resource_manager.placeholder
            placeholders = ",".join(placeholder for _ in checkpoint_ids)
            params = [thread_id] + checkpoint_ids

            delete_writes_sql = f"DELETE FROM {writes_table} WHERE thread_id = {placeholder} AND checkpoint_id IN ({placeholders})"
            delete_cp_sql = f"DELETE FROM checkpoints WHERE thread_id = {placeholder} AND checkpoint_id IN ({placeholders})"

            if not settings.EMBEDDED_MODE:
                async with conn.cursor() as cur:
                    await cur.execute(delete_writes_sql, params)
                    deleted_writes = cur.rowcount
                    await cur.execute(delete_cp_sql, params)
                    deleted_checkpoints = cur.rowcount
            else:
                await conn.execute("PRAGMA foreign_keys = OFF")
                async with conn.execute(delete_writes_sql, params) as res:
                    deleted_writes = res.rowcount
                async with conn.execute(delete_cp_sql, params) as res:
                    deleted_checkpoints = res.rowcount
                await conn.execute("PRAGMA foreign_keys = ON")
                await conn.commit()

            # Cleanup blobs (best effort)
            try:
                if settings.EMBEDDED_MODE:
                    await conn.execute("DELETE FROM checkpoint_blobs")
                else:
                    async with conn.cursor() as cur:
                        await cur.execute("DELETE FROM checkpoint_blobs")
            except Exception:
                pass

            return deleted_checkpoints, deleted_writes
