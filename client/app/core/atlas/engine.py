"""Atlas Engine - Client Mode Stub

Server-side Atlas functionality has been moved to the server branch.
Client uses cloud API for Atlas operations.
"""

import logging
from typing import Any

from app.core.atlas.models import AtlasApp, AtlasElement
from app.core.atlas.ports.store import IAtlasStore
from app.core.atlas.strategy import AppStrategy, AtlasStrategyStore, InteractionStrategy
from app.core.environment.explorers.dynamic_apps import DynamicAppTriage

logger = logging.getLogger(__name__)


class AtlasEngine:
    """
    Atlas Engine - Client Mode Stub

    Client-only implementation: Atlas operations are handled via cloud API.
    This stub maintains API compatibility but delegates to cloud.
    """

    def __init__(self, store: IAtlasStore = None):
        self.store = store
        logger.info("[AtlasEngine] Client mode - Atlas disabled, use cloud API")

    async def on_ui_tree_observed(self, event: Any) -> None:
        """Stub: UI tree observation is handled by cloud."""
        pass

    async def query_app_atlas(self, bundle_ids: str | list[str] = None, state_id: str = None, platform: str = "macos") -> str:
        """Stub: App atlas queries are handled by cloud."""
        return "Atlas queries are handled by cloud API in client mode."

    async def get_app_strategy(self, bundle_id: str, platform: str = "android") -> AppStrategy | None:
        """Get interaction strategy from local store."""
        try:
            return await AtlasStrategyStore.get_strategy(bundle_id, platform)
        except Exception as e:
            logger.error(f"[AtlasEngine] Failed to get strategy for {platform}:{bundle_id}: {e}")
            return None

    async def is_dynamic_app(self, bundle_id: str, platform: str = "android") -> bool:
        """Check if an app is marked as dynamic."""
        try:
            dynamic_apps = await DynamicAppTriage.get_dynamic_apps(platform)
            return bundle_id in dynamic_apps
        except Exception as e:
            logger.debug(f"[AtlasEngine] Dynamic app check failed: {e}")
            return False

    async def list_apps(self) -> str:
        """Stub: App listing is handled by cloud."""
        return "Atlas app listing is handled by cloud API in client mode."

    async def clear_atlas(self) -> None:
        """Stub: Atlas clearing is handled by cloud."""
        logger.info("[AtlasEngine] Atlas clearing is handled by cloud API in client mode")
