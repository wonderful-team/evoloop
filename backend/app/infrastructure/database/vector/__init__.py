"""Vector storage backends for EvoLoop.

支持项目级向量存储隔离：
- Embedded Mode: 每个 project_path 对应一个独立的 LanceVectorStore 实例
- Full Mode: 使用全局 PgVectorStore（PostgreSQL 天然支持多租户）
"""

import logging
import threading

from app.core.config import settings
from app.infrastructure.database.vector.base import BaseVectorStore

logger = logging.getLogger(__name__)

# 缓存策略：{db_path: VectorStore 实例}
# - 项目级: db_path = {project}/.evoloop/vectors/
# - 全局级: db_path = ~/.evoloop/vectors/ (用于 skills 等)
_vector_stores: dict[str, BaseVectorStore] = {}
_vector_store_lock = threading.Lock()


def get_vector_store(project_path: str | None = None) -> BaseVectorStore:
    """
    Get the vector store instance for the given project.

    Args:
        project_path: 项目本地路径（如 /Users/xujin/Projects/evoloop）。
                     Embedded Mode 下，每个 project_path 对应一个独立的 LanceVectorStore。
                     None 表示全局 vector store（用于 skills 等非项目数据）。

    Returns:
        BaseVectorStore: LanceVectorStore (embedded) 或 PgVectorStore (full mode)
    """
    if settings.EMBEDDED_MODE:
        from app.infrastructure.database.vector.lancedb_store import LanceVectorStore

        # 解析 db_path
        if project_path:
            from app.core.project.utils import get_vectors_path

            db_path = str(get_vectors_path(project_path))
        else:
            # 全局 vector store（skills 等）
            db_path = settings.LANCEDB_PATH

        # 检查缓存
        with _vector_store_lock:
            cached = _vector_stores.get(db_path)
        if cached is not None:
            return cached

        # Create the store outside the lock so the asyncio event loop is not
        # blocked by LanceDB table initialization.
        store = LanceVectorStore(db_path)

        with _vector_store_lock:
            if db_path not in _vector_stores:
                _vector_stores[db_path] = store
                logger.info(f"[VectorStore] Initialized LanceVectorStore at {db_path}")
            return _vector_stores[db_path]

    else:
        # Full Mode: PgVectorStore 是全局单例（PostgreSQL 支持多租户隔离）
        cache_key = "__pgvector__"
        with _vector_store_lock:
            cached = _vector_stores.get(cache_key)
        if cached is not None:
            return cached

        from app.infrastructure.database.vector.pgvector_store import PgVectorStore

        store = PgVectorStore()

        with _vector_store_lock:
            if cache_key not in _vector_stores:
                _vector_stores[cache_key] = store
                logger.info("[VectorStore] Initialized PgVectorStore (production mode)")
            return _vector_stores[cache_key]


def get_skills_store() -> BaseVectorStore:
    """
    Get the global skills vector store.

    Skills 是用户级数据，跨项目共享，始终使用全局 vector store。
    """
    return get_vector_store(project_path=None)


def reset_vector_store() -> None:
    """Reset all vector store instances (useful for testing)."""
    global _vector_stores
    with _vector_store_lock:
        _vector_stores.clear()
    logger.debug("[VectorStore] All vector stores reset")


__all__ = [
    "BaseVectorStore",
    "get_vector_store",
    "get_skills_store",
    "reset_vector_store",
]
