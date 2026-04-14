import logging

from sqlmodel import Session, create_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create appropriate engine based on mode
if settings.EMBEDDED_MODE:
    # Use standard sqlite3 for sync operations (initial_data.py)
    # The async engine for lifespan() is in app.infrastructure.database.sql.database
    sync_sqlite_path = settings.SQLITE_PATH
    engine = create_engine(f"sqlite:///{sync_sqlite_path}")
    logger.debug(f"[db] Using sync SQLite engine for embedded mode: {sync_sqlite_path}")
else:
    # PostgreSQL
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    """Initialize database tables.

    - Embedded Mode (SQLite): Tables are created in lifespan() - no-op here
    - Full Mode (PostgreSQL): Use Alembic migrations (manual)
    """
    if settings.EMBEDDED_MODE:
        # Tables are already created in main.py lifespan() using async engine
        # This function is called from initial_data.py for seeding data only
        logger.debug("[init_db] Embedded mode: Tables already created in lifespan, skipping...")
    else:
        # Full mode: Tables should be created with Alembic migrations
        logger.info("[init_db] Full mode: Use Alembic migrations (alembic upgrade head)")
