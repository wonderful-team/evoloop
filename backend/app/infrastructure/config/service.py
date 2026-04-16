import logging
from typing import Callable, Awaitable

from sqlmodel import Session, select

from app.core.db import engine
from app.models.system import SystemConfig
from app.core.events import system_bus, SystemEventType, BaseEvent

logger = logging.getLogger(__name__)
_cache: dict[str, str] = {}
_change_handlers: dict[str, list[Callable[[str, str], Awaitable[None]]]] = {}


class SystemConfigService:
    @staticmethod
    def get_value(key: str, default: str | None = None) -> str | None:
        if key in _cache:
            return _cache[key]

        with Session(engine) as session:
            config = session.get(SystemConfig, key)
            if config:
                val = config.value
                _cache[key] = val
                return val
            return default

    @staticmethod
    def set_value(key: str, value: str, description: str | None = None) -> SystemConfig:
        with Session(engine) as session:
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

            # Update cache
            _cache[key] = value
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
                    try:
                        await handler(old_value, value)
                    except Exception as e:
                        logger.error(f"Change handler failed for {key}: {e}")
            
            # 2. Publish System Event (New Decoupled Approach)
            try:
                await system_bus.publish(BaseEvent(
                    event_type=SystemEventType.CONFIG_CHANGED,
                    source="SystemConfigService",
                    data={
                        "key": key,
                        "old_value": old_value,
                        "new_value": value
                    }
                ))
                logger.info(f"Published CONFIG_CHANGED event for {key}")
            except Exception as e:
                logger.error(f"Failed to publish CONFIG_CHANGED event: {e}")

        return config

    @staticmethod
    def get_all() -> list[SystemConfig]:
        with Session(engine) as session:
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
