import logging
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy.orm import DeclarativeBase, Session

from app.infrastructure.database.resource_manager import db_resource_manager

logger = logging.getLogger(__name__)


class DatabaseResourceProxy:
    """
    Proxy object that delegates all calls and attribute access to the actual
    database resource (engine or session factory) only when used.

    This solves the 'import-time capture of None' problem.
    """

    def __init__(self, resource_name: str):
        self._resource_name = resource_name

    def _get_resource(self):
        if self._resource_name == "engine":
            res = db_resource_manager.engine
        elif self._resource_name == "AsyncSessionLocal":
            res = db_resource_manager.session_factory
        else:
            raise AttributeError(f"Unknown resource name: {self._resource_name}")

        if res is None:
            raise RuntimeError(
                f"Database {self._resource_name} accessed before initialization. "
                "Ensure await db_resource_manager.initialize() has completed."
            )
        return res

    def __call__(self, *args, **kwargs):
        # Delegate calling (e.g., AsyncSessionLocal())
        return self._get_resource()(*args, **kwargs)

    def __getattr__(self, name):
        # Delegate attribute access (e.g., engine.connect())
        return getattr(self._get_resource(), name)

    def __repr__(self):
        return f"<DatabaseResourceProxy for {self._resource_name}>"


# --- Dynamic Module-Level Proxy (Python 3.7+) ---
def __getattr__(name):
    if name == "engine":
        return DatabaseResourceProxy("engine")
    if name == "AsyncSessionLocal":
        return DatabaseResourceProxy("AsyncSessionLocal")
    raise AttributeError(f"module {__name__} has no attribute {name}")


# For backward compatibility
get_engine = lambda: db_resource_manager.engine


# Base Model
class Base(DeclarativeBase):
    # Suppress warnings about delete operations that match 0 rows
    # This can happen with concurrent deletes or when the row is already deleted
    __mapper_args__ = {"confirm_deleted_rows": False}


# Dependency for FastAPI
async def get_db():
    async with db_resource_manager.session_factory() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def session_scope():
    """
    Provide a transactional scope around a series of operations.
    """
    async with db_resource_manager.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def sync_session_scope():
    """
    Synchronous session scope for use in non-async contexts
    (e.g. ContextPlugin.hydrate which is sync).
    """
    engine = db_resource_manager.sync_engine
    if engine is None:
        raise RuntimeError("sync_engine accessed before initialization")
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
