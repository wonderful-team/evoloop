import json
import os
from pathlib import Path
from typing import Any

from app.domain.system.service import SystemConfigService
from app.logging import logger


class I18nService:
    _instance = None
    _locales: dict[str, dict] = {}
    _default_lang = "en"
    _loaded = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(I18nService, cls).__new__(cls)
        return cls._instance

    def load_locales(self):
        """Load all JSON files from locales directory."""
        if self._loaded:
            return

        base_path = Path(__file__).parent / "locales"
        if not base_path.exists():
            logger.warning(f"Locales directory not found: {base_path}")
            return

        for code in ["en", "zh"]:
            file_path = base_path / f"{code}.json"
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        self._locales[code] = json.load(f)
                    logger.info(f"Loaded locale: {code}")
                except Exception as e:
                    logger.error(f"Failed to load locale {code}: {e}")
        
        self._loaded = True

    def get(self, key: str, **kwargs) -> str:
        """
        Get localized string by key (dot notation).
        Example: i18n.get("prompts.tasks.objective", title="Foo")
        """
        if not self._loaded:
            self.load_locales()

        # 1. Determine Language
        # Try to get from kwargs first (override), then system config
        lang = kwargs.pop("lang", None)
        if not lang:
            # We use "zh" as default if SystemConfig isn't set, per previous logic
            lang = SystemConfigService.get_value("LANGUAGE", "zh")

        # 2. Fetch Template
        template = self._get_template(lang, key)
        
        # Fallback to English if not found in target language
        if template is None and lang != "en":
            template = self._get_template("en", key)

        # Fallback to key if still not found
        if template is None:
            logger.debug(f"Missing translation for key: {key} (lang={lang})")
            return key

        # 3. Format
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing placeholder in i18n string '{key}': {e}")
            return template
        except Exception as e:
            logger.error(f"Error formatting i18n string '{key}': {e}")
            return template

    def _get_template(self, lang: str, key: str) -> str | None:
        """Navigate the nested dict."""
        data = self._locales.get(lang)
        if not data:
            return None

        keys = key.split(".")
        current = data
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        
        return current if isinstance(current, str) else None


# Singleton instance
i18n = I18nService()
