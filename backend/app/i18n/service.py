import json
import logging
from pathlib import Path
from typing import Any

from app.constants import LANGUAGE_MAP
from app.infrastructure.config.service import SystemConfigService

logger = logging.getLogger(__name__)


class I18nService:
    _instance = None
    _locales: dict[str, dict] = {}
    _default_lang = "en"
    _loaded = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_locales(self):
        """Load all JSON files from locales directory."""
        if self._loaded:
            return

        base_path = Path(__file__).parent / "locales"
        if not base_path.exists():
            logger.warning(f"Locales directory not found: {base_path}")
            return

        # Use LANGUAGE_MAP to determine which locales to attempt to load
        for code in LANGUAGE_MAP.keys():
            file_path = base_path / f"{code}.json"
            if file_path.exists():
                try:
                    with open(file_path, encoding="utf-8") as f:
                        self._locales[code] = json.load(f)
                    logger.info(f"Loaded locale: {code}")
                except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                    logger.error(f"Failed to load locale {code}: {e}")

        self._loaded = True

    def get(self, key: str, default=None, context=None, **kwargs) -> Any:
        """
        Get localized value by key (dot notation).
        Example: i18n.get("tasks.objective", title="Foo")

        Use `default` kwarg to specify a fallback value when key is not found.
        Use `context` dict to pass template variables safely (avoids keyword
        conflicts with parameter names like `key` or `lang`).
        """
        if not self._loaded:
            self.load_locales()

        # Merge context dict into kwargs to avoid keyword argument conflicts
        if context:
            kwargs = {**context, **kwargs}

        # 1. Determine Language
        lang = kwargs.get("lang")
        if not lang:
            lang = SystemConfigService.get_value("LANGUAGE", "zh")
            kwargs["lang"] = lang

        # 2. Fetch Value
        value = self._get_template(lang, key)

        # Fallback to English if not found in target language
        if value is None and lang != "en":
            value = self._get_template("en", key)

        # Fallback to default or key if still not found
        if value is None:
            logger.debug(f"Missing translation for key: {key} (lang={lang})")
            return default if default is not None else key

        # 3. Handle dictionaries (no formatting)
        if isinstance(value, dict):
            return value
        
        # 4. Handle lists (no formatting for now)
        if isinstance(value, list):
            return value

        # 5. Format strings
        if isinstance(value, str):
            try:
                # Support optional blocks: [[ prefix {key} suffix ]]
                # This only renders the block if {key} is present and non-empty in kwargs
                def replace_optional(match):
                    content = match.group(1)
                    # Find all placeholders in this block
                    placeholders = re.findall(r'\{(\w+)\}', content)
                    if not placeholders:
                        return content
                    
                    # If all placeholders in this block are present, render it
                    if all(kwargs.get(p) is not None for p in placeholders):
                        return content.format(**kwargs)
                    return ""

                import re
                value = re.sub(r'\[\[(.*?)\]\]', replace_optional, value)
                
                # Standard format for the remaining string
                # We use a custom formatter that ignores missing keys instead of erroring
                class SafeFormatter(dict):
                    def __missing__(self, key):
                        return "{" + key + "}"
                
                return value.format_map(SafeFormatter(**kwargs))
                
            except (ValueError, OSError, RuntimeError, TypeError, KeyError, AttributeError) as e:
                logger.error(f"Error formatting i18n string '{key}': {e}")
                return value
        
        return value

    def _get_template(self, lang: str, key: str) -> Any:
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

        return current


# Singleton instance
i18n = I18nService()
