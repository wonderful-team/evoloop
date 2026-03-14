"""SQLite-based preferences storage for Client mode.

Server mode uses Neo4j, but client mode uses SQLite for local storage.
"""

import logging
from typing import Any

from sqlalchemy import select
from app.infrastructure.database.sql.database import session_scope
from app.models.config import SystemConfig

logger = logging.getLogger(__name__)


class SqlPreferenceStore:
    """
    SQLite-based preference storage for Client mode.

    Stores user preferences in the SystemConfig table.
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize preferences store."""
        self._initialized = True
        logger.debug("[SqlPreferenceStore] Initialized")

    async def get_merged_preferences(self, context: str = None) -> dict[str, Any]:
        """
        Get merged preferences for a context.

        Args:
            context: Optional context to filter preferences

        Returns:
            Dictionary of preference key-value pairs
        """
        try:
            async with session_scope() as session:
                stmt = select(SystemConfig)
                result = await session.execute(stmt)
                configs = result.scalars().all()

                # Convert to dict, filtering by context if specified
                prefs = {}
                for config in configs:
                    if context and not config.key.startswith(f"{context}."):
                        continue
                    prefs[config.key] = config.value

                return prefs
        except Exception as e:
            logger.warning(f"[SqlPreferenceStore] Failed to get preferences: {e}")
            return {}

    async def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a single preference value."""
        try:
            async with session_scope() as session:
                stmt = select(SystemConfig).where(SystemConfig.key == key)
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()
                return config.value if config else default
        except Exception as e:
            logger.warning(f"[SqlPreferenceStore] Failed to get preference {key}: {e}")
            return default

    async def set_preference(self, key: str, value: Any, description: str = None) -> bool:
        """Set a preference value."""
        try:
            async with session_scope() as session:
                stmt = select(SystemConfig).where(SystemConfig.key == key)
                result = await session.execute(stmt)
                config = result.scalar_one_or_none()

                if config:
                    config.value = str(value)
                else:
                    config = SystemConfig(
                        key=key,
                        value=str(value),
                        description=description or f"Preference: {key}"
                    )
                    session.add(config)

                return True
        except Exception as e:
            logger.error(f"[SqlPreferenceStore] Failed to set preference {key}: {e}")
            return False

    async def flush(self) -> None:
        """Flush pending operations (no-op for SQLite)."""
        pass
