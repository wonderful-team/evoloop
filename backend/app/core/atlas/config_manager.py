"""
Atlas Configuration Manager

Manages dynamic configurations for Atlas system:
- App name to bundle ID mappings
- Dynamic app classifications
- Default interaction strategies

All configurations are stored in cache (for fast lookup).
App name -> bundle ID mappings can be re-detected from the system at any time,
so no database persistence is needed.
"""

import logging
from typing import Any

from app.constants import CACHE_KEY_DYNAMIC_APPS_PREFIX
from app.core.atlas.constants import CACHE_KEY_APP_NAME_MAP
from app.infrastructure.cache import cache

logger = logging.getLogger(__name__)


class AtlasConfigManager:
    """Centralized configuration manager for Atlas system."""

    @staticmethod
    async def get_bundle_id(app_name: str) -> str | None:
        """Get bundle ID from app name (cache first, fallback to system detection)."""
        if not app_name:
            return None

        # 1. Try cache
        try:
            bundle_id = await cache.hget(CACHE_KEY_APP_NAME_MAP, app_name)
            if bundle_id:
                return bundle_id
        except Exception as e:
            logger.debug(f"[AtlasConfig] Cache lookup failed: {e}", exc_info=True)

        # 2. Try auto-detection for macOS
        return await AtlasConfigManager._detect_bundle_id(app_name)

    @staticmethod
    async def _detect_bundle_id(app_name: str) -> str | None:
        """Auto-detect bundle ID from system (macOS only)."""
        import subprocess

        try:
            result = subprocess.run(
                ["osascript", "-e", f'id of app "{app_name}"'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                bundle_id = result.stdout.strip()
                # Cache in cache for future use
                await AtlasConfigManager.set_app_name_mapping(app_name, bundle_id)
                return bundle_id
        except Exception as e:
            logger.debug(
                f"[AtlasConfig] Bundle ID detection failed for {app_name}: {e}",
                exc_info=True,
            )
        return None

    @staticmethod
    async def set_app_name_mapping(app_name: str, bundle_id: str):
        """Add or update app name to bundle ID mapping (cache only)."""
        try:
            await cache.hset(CACHE_KEY_APP_NAME_MAP, app_name, bundle_id)
            logger.info(f"[AtlasConfig] Mapped '{app_name}' -> '{bundle_id}'")
        except Exception as e:
            logger.exception(f"[AtlasConfig] Failed to set mapping: {e}")

    @staticmethod
    def _get_dynamic_apps_key(platform: str) -> str:
        """Generate platform-specific key for dynamic apps set."""
        return f"{CACHE_KEY_DYNAMIC_APPS_PREFIX}:{platform}"

    @staticmethod
    async def get_dynamic_apps(platform: str = "android") -> set[str]:
        """Get all dynamic app bundle IDs from cache for a specific platform."""
        try:
            key = AtlasConfigManager._get_dynamic_apps_key(platform)
            apps = await cache.smembers(key)
            return set(apps) if apps else set()
        except Exception as e:
            logger.exception(f"[AtlasConfig] Failed to get dynamic apps: {e}")
            return set()

    @staticmethod
    async def is_dynamic_app(bundle_id: str | None, platform: str = "android") -> bool:
        """Check if an app is marked as dynamic for a specific platform."""
        if not bundle_id:
            return False

        dynamic_apps = await AtlasConfigManager.get_dynamic_apps(platform)
        return bundle_id in dynamic_apps

    @staticmethod
    async def get_app_strategy(
        bundle_id: str, platform: str = "android"
    ) -> dict[str, Any] | None:
        """Get default strategy for an app on a specific platform."""
        try:
            from app.core.atlas.strategy import AtlasStrategyStore

            strategy = await AtlasStrategyStore.get_strategy(bundle_id, platform)
            if strategy:
                return strategy.model_dump()
        except Exception as e:
            logger.debug(f"[AtlasConfig] Failed to get strategy: {e}", exc_info=True)
        return None

    @staticmethod
    async def initialize_defaults():
        """Initialize default configurations (called on startup)."""
        logger.info("[AtlasConfig] Initializing default configurations...")

        # 1. Initialize app name mappings (minimal defaults)
        default_mappings = {
            "WeChat": "com.tencent.xinWeChat",
            "微信": "com.tencent.xinWeChat",
            "Safari": "com.apple.Safari",
            "Chrome": "com.google.Chrome",
            "TencentMeeting": "com.tencent.meeting",
            "腾讯会议": "com.tencent.meeting",
        }

        try:
            # Check if mappings already exist
            existing = await cache.hlen(CACHE_KEY_APP_NAME_MAP)
            if existing == 0:
                await cache.hset(CACHE_KEY_APP_NAME_MAP, mapping=default_mappings)
                logger.info(
                    f"[AtlasConfig] Initialized {len(default_mappings)} app name mappings"
                )

            # 2. Initialize minimal dynamic app safeguards
            # Check macOS dynamic apps
            existing_dynamic_macos = await cache.scard(
                AtlasConfigManager._get_dynamic_apps_key("macos")
            )
            if existing_dynamic_macos == 0:
                # Add macOS WeChat as minimal safeguard
                await cache.sadd(
                    AtlasConfigManager._get_dynamic_apps_key("macos"),
                    "com.tencent.xinWeChat",
                )
                logger.info(
                    "[AtlasConfig] Initialized minimal dynamic app safeguard for macOS (WeChat)"
                )

            # Check Android dynamic apps
            existing_dynamic_android = await cache.scard(
                AtlasConfigManager._get_dynamic_apps_key("android")
            )
            if existing_dynamic_android == 0:
                # Add Android WeChat as minimal safeguard
                await cache.sadd(
                    AtlasConfigManager._get_dynamic_apps_key("android"),
                    "com.tencent.mm",
                )
                logger.info(
                    "[AtlasConfig] Initialized minimal dynamic app safeguard for Android (WeChat)"
                )

            # 3. Initialize default strategies
            from app.core.atlas.strategy import AtlasStrategyStore

            await AtlasStrategyStore.init_default_strategies()

        except Exception as e:
            logger.exception(f"[AtlasConfig] Failed to initialize defaults: {e}")


# Convenience functions for direct use
async def get_bundle_id(app_name: str) -> str | None:
    return await AtlasConfigManager.get_bundle_id(app_name)


async def is_dynamic_app(bundle_id: str | None, platform: str = "android") -> bool:
    return await AtlasConfigManager.is_dynamic_app(bundle_id, platform)
