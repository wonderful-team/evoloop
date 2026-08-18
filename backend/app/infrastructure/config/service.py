import logging
from collections.abc import Awaitable, Callable

from sqlmodel import Session, select

from app.core.events.publishers import publish_config_changed
from app.infrastructure.database.resource_manager import db_resource_manager
from app.models.system import SystemConfig

logger = logging.getLogger(__name__)
_change_handlers: dict[str, list[Callable[[str, str], Awaitable[None]]]] = {}


class SystemConfigService:
    @staticmethod
    def get_value(key: str, default: str | None = None) -> str | None:
        # Safety: Check if database is initialized
        if not db_resource_manager.sync_engine:
            return default

        with Session(db_resource_manager.sync_engine) as session:
            config = session.get(SystemConfig, key)
            if config and config.value:
                return config.value
            return default

    @staticmethod
    def set_value(key: str, value: str, description: str | None = None) -> SystemConfig:
        with Session(db_resource_manager.sync_engine) as session:
            config = session.get(SystemConfig, key)
            if not config:
                config = SystemConfig(key=key, value=value, description=description)
                session.add(config)
            else:
                config.value = value
                if description:
                    config.description = description
                session.add(config)
            session.commit()
            session.refresh(config)

            return config

    @staticmethod
    def register_change_handler(key: str, handler: Callable[[str, str], Awaitable[None]]) -> None:
        """Register a callback handler for configuration changes.

        Args:
            key: The configuration key to watch
            handler: Async callback(old_value, new_value) triggered when value changes
        """
        if key not in _change_handlers:
            _change_handlers[key] = []
        _change_handlers[key].append(handler)
        logger.debug(f"Registered change handler for {key}")

    @staticmethod
    async def set_value_async(key: str, value: str, description: str | None = None) -> SystemConfig:
        """Set configuration value asynchronously and trigger change handlers.

        This method should be used by API endpoints to ensure side effects are triggered.
        """
        # Get old value before update
        old_value = SystemConfigService.get_value(key) or ""

        # Perform the update using sync method
        config = SystemConfigService.set_value(key, value, description)

        # Trigger handlers if value actually changed
        if old_value != value:
            # 1. Trigger legacy callback handlers
            if key in _change_handlers:
                logger.info(f"Config {key} changed: '{old_value}' -> '{value}', triggering legacy handlers...")
                for handler in _change_handlers[key]:
                    await handler(old_value, value)

            # 2. Publish System Event via core layer publisher
            await publish_config_changed(key, old_value, value)
            logger.info(f"Published CONFIG_CHANGED event for {key}")

        return config

    @staticmethod
    def get_all() -> list[SystemConfig]:
        if not db_resource_manager.sync_engine:
            return []
        with Session(db_resource_manager.sync_engine) as session:
            statement = select(SystemConfig)
            return session.exec(statement).all()

    @staticmethod
    def get_language_preference() -> str:
        """
        Get the human-readable language preference for LLM prompts.
        Defaults to 'Chinese (中文)' if not set or set to 'zh'.
        """
        code = SystemConfigService.get_value("LANGUAGE", "zh")
        language_map = {
            "zh": "Chinese (中文)",
            "en": "English",
            "ja": "Japanese (日本語)",
            # Add more as needed
        }
        return language_map.get(code, code)
