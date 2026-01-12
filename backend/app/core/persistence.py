
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

_db_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None

def set_db_pool(pool: AsyncConnectionPool):
    global _db_pool
    _db_pool = pool

def get_db_pool() -> AsyncConnectionPool | None:
    return _db_pool

def set_checkpointer(saver: AsyncPostgresSaver):
    global _checkpointer
    _checkpointer = saver

def get_checkpointer() -> AsyncPostgresSaver | None:
    return _checkpointer
