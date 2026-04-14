"""
Atlas Strategy Storage - For dynamic apps, stores "how to find" not "where".

Dynamic apps (WeChat, browsers, etc) have coordinate-unstable UI.
Instead of storing coordinates, we store interaction strategies.
"""

import json
import logging

from pydantic import Field

from app.infrastructure.cache import cache
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)

REDIS_KEY_ATLAS_STRATEGIES = "atlas:strategies"


class StrategyParameters(DynamicBaseModel):
    pass


class AppHints(DynamicBaseModel):
    pass


class InteractionStrategy(DynamicBaseModel):
    """
    A strategy for finding/interacting with an element.
    Examples: "search_then_click", "scroll_until_visible", "static_click"
    """
    strategy_type: str  # "search_then_click", "scroll_until_visible", etc.
    target_element: str  # What we're looking for (e.g., "Alice", "Send button")

    # Strategy-specific parameters
    parameters: StrategyParameters = Field(default_factory=StrategyParameters)

    # Reliability metrics
    success_count: int = 0
    fail_count: int = 0

    @property
    def reliability_score(self) -> float:
        """Calculate reliability based on historical usage."""
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.5  # Unknown, default to neutral
        return self.success_count / total

    def to_dict(self) -> dict:
        """Convert to dictionary including computed property."""
        data = self.model_dump()
        data["reliability_score"] = self.reliability_score
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionStrategy":
        return cls.model_validate(data)


class AppStrategy(DynamicBaseModel):
    """
    Complete strategy set for a dynamic app.
    Stores infrastructure elements (static) and interaction strategies.
    """
    bundle_id: str
    platform: str

    # Static infrastructure elements (toolbars, search bars, etc)
    infrastructure: list[dict] = Field(default_factory=list)

    # Known interaction strategies
    strategies: list[InteractionStrategy] = Field(default_factory=list)

    # App-specific hints
    hints: AppHints = Field(default_factory=AppHints)

    def get_strategy_for(self, target: str) -> InteractionStrategy | None:
        """Find the best strategy for a target element."""
        matching = [s for s in self.strategies if s.target_element.lower() == target.lower()]
        if not matching:
            return None
        # Return the most reliable strategy
        return max(matching, key=lambda s: s.reliability_score)

    def get_infrastructure_element(self, role: str) -> dict | None:
        """Find an infrastructure element by role or label."""
        for elem in self.infrastructure:
            if elem.get("role") == role or elem.get("label") == role:
                return elem
        return None

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "AppStrategy":
        return cls.model_validate(data)


class AtlasStrategyStore:
    """
    Cache-backed storage for app strategies.
    Platform-specific to avoid conflicts between different OS versions.
    """

    @staticmethod
    def _get_key(bundle_id: str, platform: str) -> str:
        """Generate platform-specific cache key."""
        return f"{REDIS_KEY_ATLAS_STRATEGIES}:{platform}:{bundle_id}"

    @classmethod
    async def get_strategy(cls, bundle_id: str, platform: str = "android") -> AppStrategy | None:
        """Retrieve strategy for an app."""
        key = cls._get_key(bundle_id, platform)
        try:
            data = await cache.get(key)
            if data:
                return AppStrategy.from_dict(json.loads(data))
        except Exception as e:
            logger.warning(f"Failed to load strategy for {bundle_id}: {e}")
        return None

    @classmethod
    async def save_strategy(cls, strategy: AppStrategy) -> bool:
        """Save strategy for an app."""
        key = cls._get_key(strategy.bundle_id, strategy.platform)
        try:
            await cache.set(key, json.dumps(strategy.to_dict()), ex=86400 * 7)  # 7 days
            return True
        except Exception as e:
            logger.error(f"Failed to save strategy for {strategy.bundle_id}: {e}")
            return False

    @classmethod
    async def delete_strategy(cls, bundle_id: str, platform: str = "android") -> bool:
        """Delete strategy for an app."""
        key = cls._get_key(bundle_id, platform)
        try:
            await cache.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete strategy for {bundle_id}: {e}")
            return False

    @classmethod
    async def init_default_strategies(cls):
        """Initialize default strategies for common apps."""
        logger.info("[AtlasStrategy] Initializing default strategies...")
        # Common apps with known stable infrastructure
        defaults = [
            AppStrategy(
                bundle_id="com.tencent.xinWeChat",
                platform="macos",
                hints={"has_search_bar": True, "search_bar_location": "top"}
            ),
            AppStrategy(
                bundle_id="com.apple.Safari",
                platform="macos",
                hints={"has_search_bar": True}
            )
        ]
        for s in defaults:
            await cls.save_strategy(s)
