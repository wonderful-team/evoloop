"""Atlas Strategy Storage - SQLite implementation for Client-only architecture.

Dynamic apps (WeChat, browsers, etc) have coordinate-unstable UI.
Instead of storing coordinates, we store interaction strategies.

Note: Previously used Redis, now uses SQLite for Client-only persistence.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import engine
from app.models.atlas import AtlasStrategy

logger = logging.getLogger(__name__)


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
    SQLite-backed storage for app strategies.
    Replaces Redis storage for Client-only architecture.
    """

    @staticmethod
    async def save_strategy(app_strategy: AppStrategy) -> None:
        """Save an app strategy to SQLite."""
        try:
            with Session(engine) as session:
                # Check if exists
                stmt = select(AtlasStrategy).where(
                    AtlasStrategy.bundle_id == app_strategy.bundle_id,
                    AtlasStrategy.platform == app_strategy.platform,
                )
                existing = session.execute(stmt).scalar_one_or_none()

                if existing:
                    # Update
                    existing.set_infrastructure(app_strategy.infrastructure)
                    existing.set_strategies([s.to_dict() for s in app_strategy.strategies])
                    existing.set_hints(app_strategy.hints)
                    logger.info(
                        f"[AtlasStrategyStore] Updated strategy for {app_strategy.platform}:{app_strategy.bundle_id}"
                    )
                else:
                    # Create new
                    new_strategy = AtlasStrategy(
                        bundle_id=app_strategy.bundle_id,
                        platform=app_strategy.platform,
                    )
                    new_strategy.set_infrastructure(app_strategy.infrastructure)
                    new_strategy.set_strategies([s.to_dict() for s in app_strategy.strategies])
                    new_strategy.set_hints(app_strategy.hints)
                    session.add(new_strategy)
                    logger.info(
                        f"[AtlasStrategyStore] Created strategy for {app_strategy.platform}:{app_strategy.bundle_id}"
                    )

                session.commit()
        except Exception as e:
            logger.error(f"[AtlasStrategyStore] Failed to save strategy: {e}")
            raise

    @staticmethod
    async def get_strategy(bundle_id: str, platform: str = "android") -> AppStrategy | None:
        """Retrieve an app strategy from SQLite."""
        try:
            with Session(engine) as session:
                stmt = select(AtlasStrategy).where(
                    AtlasStrategy.bundle_id == bundle_id,
                    AtlasStrategy.platform == platform,
                )
                record = session.execute(stmt).scalar_one_or_none()

                if record:
                    return AppStrategy(
                        bundle_id=record.bundle_id,
                        platform=record.platform,
                        infrastructure=record.get_infrastructure(),
                        strategies=[
                            InteractionStrategy.from_dict(s) for s in record.get_strategies()
                        ],
                        hints=record.get_hints(),
                    )
                return None
        except Exception as e:
            logger.error(f"[AtlasStrategyStore] Failed to get strategy: {e}")
            return None

    @staticmethod
    async def delete_strategy(bundle_id: str, platform: str = "android") -> None:
        """Delete an app strategy from SQLite."""
        try:
            with Session(engine) as session:
                stmt = select(AtlasStrategy).where(
                    AtlasStrategy.bundle_id == bundle_id,
                    AtlasStrategy.platform == platform,
                )
                record = session.execute(stmt).scalar_one_or_none()

                if record:
                    session.delete(record)
                    session.commit()
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
