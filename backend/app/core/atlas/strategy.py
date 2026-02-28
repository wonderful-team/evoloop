"""
Atlas Strategy Storage - For dynamic apps, stores "how to find" not "where".

Dynamic apps (WeChat, browsers, etc) have coordinate-unstable UI.
Instead of storing coordinates, we store interaction strategies.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.infrastructure.database.redis import get_redis_client

logger = logging.getLogger(__name__)

REDIS_KEY_ATLAS_STRATEGIES = "atlas:strategies"


@dataclass
class InteractionStrategy:
    """
    A strategy for finding/interacting with an element.
    Examples: "search_then_click", "scroll_until_visible", "static_click"
    """
    strategy_type: str  # "search_then_click", "scroll_until_visible", "static_click", "menu_navigate"
    target_element: str  # What we're looking for (e.g., "Alice", "Send button")

    # Strategy-specific parameters
    parameters: dict[str, Any] = field(default_factory=dict)
    # Example for search_then_click:
    #   {"search_bar_id": "com.x:id/search", "result_container": "com.x:id/results"}
    # Example for scroll_until_visible:
    #   {"scroll_container": "com.x:id/list", "scroll_direction": "vertical"}

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
        return {
            "strategy_type": self.strategy_type,
            "target_element": self.target_element,
            "parameters": self.parameters,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "reliability_score": self.reliability_score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InteractionStrategy":
        return cls(
            strategy_type=data["strategy_type"],
            target_element=data["target_element"],
            parameters=data.get("parameters", {}),
            success_count=data.get("success_count", 0),
            fail_count=data.get("fail_count", 0),
        )


@dataclass
class AppStrategy:
    """
    Complete strategy set for a dynamic app.
    Stores infrastructure elements (static) and interaction strategies.
    """
    bundle_id: str
    platform: str

    # Static infrastructure elements (toolbars, search bars, etc)
    infrastructure: list[dict] = field(default_factory=list)

    # Known interaction strategies
    strategies: list[InteractionStrategy] = field(default_factory=list)

    # App-specific hints
    hints: dict[str, Any] = field(default_factory=dict)
    # Example:
    #   {
    #       "has_search_bar": True,
    #       "search_bar_location": "top",
    #       "main_list_container": "com.tencent.mm:id/conversation_list",
    #       "common_actions": ["search_contact", "open_chat"]
    #   }

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
        return {
            "bundle_id": self.bundle_id,
            "platform": self.platform,
            "infrastructure": self.infrastructure,
            "strategies": [s.to_dict() for s in self.strategies],
            "hints": self.hints,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppStrategy":
        return cls(
            bundle_id=data["bundle_id"],
            platform=data.get("platform", "android"),
            infrastructure=data.get("infrastructure", []),
            strategies=[InteractionStrategy.from_dict(s) for s in data.get("strategies", [])],
            hints=data.get("hints", {}),
        )


class AtlasStrategyStore:
    """
    Redis-backed storage for app strategies.
    Platform-specific to avoid conflicts between different OS versions.
    """

    @staticmethod
    def _get_key(bundle_id: str, platform: str) -> str:
        """Generate platform-specific Redis key."""
        return f"{REDIS_KEY_ATLAS_STRATEGIES}:{platform}:{bundle_id}"

    @staticmethod
    async def save_strategy(app_strategy: AppStrategy) -> None:
        """Save an app strategy to Redis."""
        try:
            redis = await get_redis_client()
            key = AtlasStrategyStore._get_key(app_strategy.bundle_id, app_strategy.platform)
            await redis.set(key, json.dumps(app_strategy.to_dict()))
            logger.info(f"[AtlasStrategyStore] Saved strategy for {app_strategy.platform}:{app_strategy.bundle_id}")
        except Exception as e:
            logger.error(f"[AtlasStrategyStore] Failed to save strategy: {e}")

    @staticmethod
    async def get_strategy(bundle_id: str, platform: str = "android") -> AppStrategy | None:
        """Retrieve an app strategy from Redis."""
        try:
            redis = await get_redis_client()
            key = AtlasStrategyStore._get_key(bundle_id, platform)
            data = await redis.get(key)
            if data:
                return AppStrategy.from_dict(json.loads(data))
            return None
        except Exception as e:
            logger.error(f"[AtlasStrategyStore] Failed to get strategy: {e}")
            return None

    @staticmethod
    async def delete_strategy(bundle_id: str, platform: str = "android") -> None:
        """Delete an app strategy from Redis."""
        try:
            redis = await get_redis_client()
            key = AtlasStrategyStore._get_key(bundle_id, platform)
            await redis.delete(key)
            logger.info(f"[AtlasStrategyStore] Deleted strategy for {platform}:{bundle_id}")
        except Exception as e:
            logger.error(f"[AtlasStrategyStore] Failed to delete strategy: {e}")

    @staticmethod
    async def init_default_strategies():
        """Initialize default strategies from configuration (no hardcoding)."""
        # WeChat Android
        wechat_android = await AtlasStrategyStore.get_strategy("com.tencent.mm", "android")
        if not wechat_android:
            default = AppStrategy(
                bundle_id="com.tencent.mm",
                platform="android",
                infrastructure=[
                    {"role": "search_bar", "label": "搜索"},
                ],
                strategies=[
                    InteractionStrategy(
                        strategy_type="search_then_click",
                        target_element="find_conversation",
                        parameters={"input_method": "type"},
                    ),
                ],
                hints={"has_search_bar": True, "coordinate_unstable": True},
            )
            await AtlasStrategyStore.save_strategy(default)
            logger.info("[AtlasStrategyStore] Initialized default WeChat (Android) strategy")

        # WeChat macOS
        wechat_macos = await AtlasStrategyStore.get_strategy("com.tencent.xinWeChat", "macos")
        if not wechat_macos:
            default = AppStrategy(
                bundle_id="com.tencent.xinWeChat",
                platform="macos",
                infrastructure=[
                    {"role": "search_bar", "label": "搜索"},
                ],
                strategies=[
                    InteractionStrategy(
                        strategy_type="search_then_click",
                        target_element="find_conversation",
                        parameters={"input_method": "type"},
                    ),
                ],
                hints={"has_search_bar": True, "coordinate_unstable": True},
            )
            await AtlasStrategyStore.save_strategy(default)
            logger.info("[AtlasStrategyStore] Initialized default WeChat (macOS) strategy")
