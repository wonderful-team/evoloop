from sqlmodel import Session, select

from app.core.db import engine
from app.models.config import SystemConfig


class SystemConfigService:
    @staticmethod
    def get_value(key: str, default: str | None = None) -> str | None:
        with Session(engine) as session:
            config = session.get(SystemConfig, key)
            if config:
                return config.value
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
