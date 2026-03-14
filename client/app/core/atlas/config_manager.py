"""Atlas Configuration Manager - SQLite implementation for Client-only architecture.

Manages dynamic configurations for Atlas system:
- App name to bundle ID mappings
- Dynamic app classifications
- Default interaction strategies

All configurations are stored in SQLite (replaces Redis for Client-only architecture).
"""

import logging
import subprocess
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import engine
from app.models.atlas import AtlasAppNameMapping, AtlasDynamicApp
from app.models.config import SystemConfig

logger = logging.getLogger(__name__)


class AtlasConfigManager:
    """Centralized configuration manager for Atlas system (SQLite-backed)."""

    @staticmethod
    async def get_bundle_id(app_name: str) -> str | None:
        """Get bundle ID from app name (SQLite first, fallback to system detection)."""
        if not app_name:
            return None

        # 1. Try SQLite
        try:
            with Session(engine) as session:
                stmt = select(AtlasAppNameMapping).where(
                    AtlasAppNameMapping.app_name == app_name
                )
                mapping = session.execute(stmt).scalar_one_or_none()
                if mapping:
                    return mapping.bundle_id
        except Exception as e:
            logger.debug(f"[AtlasConfig] SQLite lookup failed: {e}")

        # 2. Try auto-detection for macOS
        return await AtlasConfigManager._detect_bundle_id(app_name)

    @staticmethod
    async def _detect_bundle_id(app_name: str) -> str | None:
        """Auto-detect bundle ID from system (macOS only)."""
        try:
            result = subprocess.run(
                ["osascript", "-e", f'id of app "{app_name}"'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                bundle_id = result.stdout.strip()
                # Cache in SQLite for future use
                await AtlasConfigManager.set_app_name_mapping(app_name, bundle_id)
                return bundle_id
        except Exception as e:
            logger.debug(f"[AtlasConfig] Bundle ID detection failed for {app_name}: {e}")
        return None

    @staticmethod
    async def set_app_name_mapping(app_name: str, bundle_id: str, persist: bool = True):
        """Add or update app name to bundle ID mapping."""
        try:
            with Session(engine) as session:
                # Check if exists
                stmt = select(AtlasAppNameMapping).where(
                    AtlasAppNameMapping.app_name == app_name
                )
                existing = session.execute(stmt).scalar_one_or_none()

                if existing:
                    existing.bundle_id = bundle_id
                    logger.info(f"[AtlasConfig] Updated '{app_name}' -> '{bundle_id}'")
                else:
                    new_mapping = AtlasAppNameMapping(
                        app_name=app_name,
                        bundle_id=bundle_id,
                    )
                    session.add(new_mapping)
                    logger.info(f"[AtlasConfig] Created '{app_name}' -> '{bundle_id}'")

                session.commit()

                # Also persist to SystemConfig (legacy compatibility)
                if persist:
                    config_key = f"atlas:app_name:{app_name}"
                    existing_config = session.get(SystemConfig, config_key)
                    if existing_config:
                        existing_config.value = bundle_id
                    else:
                        session.add(SystemConfig(
                            key=config_key,
                            value=bundle_id,
                            description=f"Atlas: App name '{app_name}' -> Bundle ID"
                        ))
                    session.commit()

        except Exception as e:
            logger.error(f"[AtlasConfig] Failed to set mapping: {e}")

    @staticmethod
    async def remove_app_name_mapping(app_name: str):
        """Remove app name mapping."""
        try:
            with Session(engine) as session:
                # Remove from AtlasAppNameMapping
                stmt = select(AtlasAppNameMapping).where(
                    AtlasAppNameMapping.app_name == app_name
                )
                mapping = session.execute(stmt).scalar_one_or_none()
                if mapping:
                    session.delete(mapping)

                # Remove from SystemConfig (legacy)
                config_key = f"atlas:app_name:{app_name}"
                existing = session.get(SystemConfig, config_key)
                if existing:
                    session.delete(existing)

                session.commit()
                logger.info(f"[AtlasConfig] Removed mapping for '{app_name}'")
        except Exception as e:
            logger.error(f"[AtlasConfig] Failed to remove mapping: {e}")

    @staticmethod
    async def get_dynamic_apps(platform: str = "android") -> set[str]:
        """Get all dynamic app bundle IDs from SQLite for a specific platform."""
        try:
            with Session(engine) as session:
                stmt = select(AtlasDynamicApp.bundle_id).where(
                    AtlasDynamicApp.platform == platform
                )
                results = session.execute(stmt).scalars().all()
                return set(results)
        except Exception as e:
            logger.error(f"[AtlasConfig] Failed to get dynamic apps: {e}")
            return set()

    @staticmethod
    async def mark_app_dynamic(bundle_id: str, platform: str = "android", reason: str = ""):
        """Mark an app as dynamic (coordinate-unstable)."""
        try:
            with Session(engine) as session:
                # Check if exists
                stmt = select(AtlasDynamicApp).where(
                    AtlasDynamicApp.bundle_id == bundle_id,
                    AtlasDynamicApp.platform == platform,
                )
                existing = session.execute(stmt).scalar_one_or_none()

                if existing:
                    existing.reason = reason
                else:
                    new_app = AtlasDynamicApp(
                        bundle_id=bundle_id,
                        platform=platform,
                        reason=reason,
                    )
                    session.add(new_app)

                session.commit()
                logger.info(f"[AtlasConfig] Marked '{platform}:{bundle_id}' as DYNAMIC: {reason}")
        except Exception as e:
            logger.error(f"[AtlasConfig] Failed to mark app dynamic: {e}")

    @staticmethod
    async def unmark_app_dynamic(bundle_id: str, platform: str = "android"):
        """Remove app from dynamic list."""
        try:
            with Session(engine) as session:
                stmt = select(AtlasDynamicApp).where(
                    AtlasDynamicApp.bundle_id == bundle_id,
                    AtlasDynamicApp.platform == platform,
                )
                existing = session.execute(stmt).scalar_one_or_none()

                if existing:
                    session.delete(existing)
                    session.commit()
                    logger.info(f"[AtlasConfig] Unmarked '{platform}:{bundle_id}' as dynamic")
        except Exception as e:
            logger.error(f"[AtlasConfig] Failed to unmark app: {e}")

    @staticmethod
    async def is_dynamic_app(bundle_id: str | None, platform: str = "android") -> bool:
        """Check if an app is marked as dynamic for a specific platform."""
        if not bundle_id:
            return False

        dynamic_apps = await AtlasConfigManager.get_dynamic_apps(platform)
        return bundle_id in dynamic_apps

    @staticmethod
    async def get_app_strategy(bundle_id: str, platform: str = "android") -> dict[str, Any] | None:
        """Get default strategy for an app on a specific platform."""
        try:
            from app.core.atlas.strategy import AtlasStrategyStore
            strategy = await AtlasStrategyStore.get_strategy(bundle_id, platform)
            if strategy:
                return strategy.to_dict()
        except Exception as e:
            logger.debug(f"[AtlasConfig] Failed to get strategy: {e}")
        return None

    @staticmethod
    async def set_app_strategy(bundle_id: str, strategy: dict[str, Any], platform: str = "android"):
        """Set default strategy for an app on a specific platform."""
        try:
            from app.core.atlas.strategy import AtlasStrategyStore, AppStrategy
            app_strategy = AppStrategy.from_dict(strategy)
            await AtlasStrategyStore.save_strategy(app_strategy)
            logger.info(f"[AtlasConfig] Set strategy for '{platform}:{bundle_id}'")
        except Exception as e:
            logger.error(f"[AtlasConfig] Failed to set strategy: {e}")

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
        }

        try:
            with Session(engine) as session:
                # Check if we have any mappings
                count = session.query(AtlasAppNameMapping).count()

                if count == 0:
                    # Initialize defaults
                    for app_name, bundle_id in default_mappings.items():
                        mapping = AtlasAppNameMapping(
                            app_name=app_name,
                            bundle_id=bundle_id,
                        )
                        session.add(mapping)
                    session.commit()
                    logger.info(f"[AtlasConfig] Initialized {len(default_mappings)} app name mappings")

            # 2. Initialize minimal dynamic app safeguards
            # Check macOS dynamic apps
            dynamic_macos = await AtlasConfigManager.get_dynamic_apps("macos")
            if not dynamic_macos:
                await AtlasConfigManager.mark_app_dynamic(
                    "com.tencent.xinWeChat", "macos", "Default safeguard"
                )
                logger.info("[AtlasConfig] Initialized minimal dynamic app safeguard for macOS (WeChat)")

            # Check Android dynamic apps
            dynamic_android = await AtlasConfigManager.get_dynamic_apps("android")
            if not dynamic_android:
                await AtlasConfigManager.mark_app_dynamic(
                    "com.tencent.mm", "android", "Default safeguard"
                )
                logger.info("[AtlasConfig] Initialized minimal dynamic app safeguard for Android (WeChat)")

            # 3. Initialize default strategies
            from app.core.atlas.strategy import AtlasStrategyStore
            await AtlasStrategyStore.init_default_strategies()

        except Exception as e:
            logger.error(f"[AtlasConfig] Failed to initialize defaults: {e}")


# Convenience functions for direct use
async def get_bundle_id(app_name: str) -> str | None:
    return await AtlasConfigManager.get_bundle_id(app_name)


async def is_dynamic_app(bundle_id: str | None, platform: str = "android") -> bool:
    return await AtlasConfigManager.is_dynamic_app(bundle_id, platform)
