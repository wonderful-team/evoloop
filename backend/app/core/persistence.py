from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from psycopg_pool import AsyncConnectionPool

_db_pool: "AsyncConnectionPool | None" = None
_checkpointer: "AsyncPostgresSaver | AsyncSqliteSaver | None" = None


def set_db_pool(pool: "AsyncConnectionPool"):
    global _db_pool
    _db_pool = pool


def get_db_pool() -> "AsyncConnectionPool | None":
    return _db_pool


def set_checkpointer(saver: "AsyncPostgresSaver | AsyncSqliteSaver"):
    global _checkpointer
    _checkpointer = saver


def get_checkpointer() -> "AsyncPostgresSaver | AsyncSqliteSaver | None":
    return _checkpointer
