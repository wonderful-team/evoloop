import logging

from sqlalchemy import text

from app.core.config import settings
from app.infrastructure.database.sql.database import get_db_session

logger = logging.getLogger(__name__)


async def wipe_knowledge_base(project_path: str | None = None):
    """
    Wipes all SQL indexed data and Vector Index tables.
    Preserves User/Project metadata.
    """
    scope = f"project: {project_path}" if project_path else "global"
    logger.warning(f"[EvoLoop] Starting Knowledge Base Reset ({scope})...")

    # SQL / Vector Store Cleanup
    try:
        from app.infrastructure.database.vector import get_vector_store

        async with get_db_session() as session:
            tables_to_truncate = [
                "code_chunks",
                "code_relations",
                "code_entities",
                "source_files",
                "tools",
            ]

            for t in tables_to_truncate:
                try:
                    if settings.EMBEDDED_MODE:
                        await session.execute(text(f"DELETE FROM {t};"))
                    else:
                        await session.execute(text(f"TRUNCATE TABLE {t} CASCADE;"))
                except Exception as e:
                    logger.warning(f"SQL: Error truncating {t}: {e}")

            logger.info(f"✅ SQL: Truncated tables: {tables_to_truncate}")

        # Vector store (per-project or global)
        vector_store = get_vector_store(project_path=project_path)
        vector_store.truncate_all()
        logger.info(f"✅ Vector Store: All data truncated ({scope})")

    except Exception as e:
        logger.error(f"Failed to wipe SQL/Vector store: {e}")
        raise e

    logger.info(f"✨ Knowledge Base Reset Complete ({scope}).")
    return True
