"""
Fixed AsyncSqliteSaver that does not force WAL mode in setup().

This allows the database to use whatever journal_mode was configured
at connection time (e.g. DELETE mode), preventing conflicts when
switching from WAL to DELETE on an existing database.
"""

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


class FixedAsyncSqliteSaver(AsyncSqliteSaver):
    """
    Override setup() to avoid forcing PRAGMA journal_mode=WAL.
    
    The parent class unconditionally sets WAL in setup(), which causes
    'database is locked' errors when the DB is already open in another
    process or when switching journal modes.
    """

    async def setup(self) -> None:
        """Set up tables without forcing WAL mode."""
        async with self.lock:
            if self.is_setup:
                return
            await self._ensure_connected()
            async with self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    type TEXT,
                    checkpoint BLOB,
                    metadata BLOB,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                );
                CREATE TABLE IF NOT EXISTS writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL DEFAULT '',
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    idx INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    type TEXT,
                    value BLOB,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                );
                """
            ):
                await self.conn.commit()
            self.is_setup = True

    async def _ensure_connected(self):
        """Ensure connection is open."""
        # aiosqlite connections are always open unless explicitly closed
        pass
