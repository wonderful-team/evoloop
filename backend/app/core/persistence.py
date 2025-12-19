from typing import Optional
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

_db_pool: Optional[AsyncConnectionPool] = None
_checkpointer: Optional[AsyncPostgresSaver] = None

def set_db_pool(pool: AsyncConnectionPool):
    global _db_pool
    _db_pool = pool

def get_db_pool() -> Optional[AsyncConnectionPool]:
    return _db_pool

def set_checkpointer(saver: AsyncPostgresSaver):
    global _checkpointer
    _checkpointer = saver

def get_checkpointer() -> Optional[AsyncPostgresSaver]:
    return _checkpointer
