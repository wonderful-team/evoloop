"""Atlas models for SQLite storage.

Replaces Redis storage for Client-only architecture.
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base


class AtlasStrategy(Base):
    """Store app interaction strategies (replaces Redis atlas:strategies)."""

    __tablename__ = "atlas_strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bundle_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, default="android")

    # JSON data
    infrastructure: Mapped[str] = mapped_column(Text, default="[]")  # List of infrastructure elements
    strategies: Mapped[str] = mapped_column(Text, default="[]")  # List of interaction strategies
    hints: Mapped[str] = mapped_column(Text, default="{}")  # App-specific hints

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Unique constraint on bundle_id + platform
    __table_args__ = (
        UniqueConstraint("bundle_id", "platform", name="uix_strategy_bundle_platform"),
        Index("ix_atlas_strategies_bundle", "bundle_id"),
        Index("ix_atlas_strategies_platform", "platform"),
    )

    def get_infrastructure(self) -> list[dict]:
        """Parse infrastructure JSON."""
        try:
            return json.loads(self.infrastructure)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_infrastructure(self, data: list[dict]) -> None:
        """Serialize infrastructure to JSON."""
        self.infrastructure = json.dumps(data, ensure_ascii=False)

    def get_strategies(self) -> list[dict]:
        """Parse strategies JSON."""
        try:
            return json.loads(self.strategies)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_strategies(self, data: list[dict]) -> None:
        """Serialize strategies to JSON."""
        self.strategies = json.dumps(data, ensure_ascii=False)

    def get_hints(self) -> dict[str, Any]:
        """Parse hints JSON."""
        try:
            return json.loads(self.hints)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_hints(self, data: dict[str, Any]) -> None:
        """Serialize hints to JSON."""
        self.hints = json.dumps(data, ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (for AppStrategy compatibility)."""
        return {
            "bundle_id": self.bundle_id,
            "platform": self.platform,
            "infrastructure": self.get_infrastructure(),
            "strategies": self.get_strategies(),
            "hints": self.get_hints(),
        }


class AtlasDynamicApp(Base):
    """Store dynamic app classifications (replaces Redis system:dynamic_apps)."""

    __tablename__ = "atlas_dynamic_apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bundle_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, default="android")

    # Why this app is marked as dynamic
    reason: Mapped[str] = mapped_column(String(500), default="")

    # Metadata
    marked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Unique constraint on bundle_id + platform
    __table_args__ = (
        UniqueConstraint("bundle_id", "platform", name="uix_dynamic_bundle_platform"),
        Index("ix_atlas_dynamic_apps_bundle", "bundle_id"),
        Index("ix_atlas_dynamic_apps_platform", "platform"),
    )


class AtlasAppNameMapping(Base):
    """Store app name to bundle ID mappings (replaces Redis atlas:app_name_map)."""

    __tablename__ = "atlas_app_name_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    bundle_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("ix_atlas_app_name_mappings_bundle", "bundle_id"),)


class AtlasProcessedApp(Base):
    """Store apps that have been processed by LLM triage (replaces Redis system:processed_apps)."""

    __tablename__ = "atlas_processed_apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bundle_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, default="android")

    # Classification result
    is_dynamic: Mapped[bool] = mapped_column(default=False)
    reason: Mapped[str] = mapped_column(String(500), default="")

    # Metadata
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Unique constraint on bundle_id + platform
    __table_args__ = (
        UniqueConstraint("bundle_id", "platform", name="uix_processed_bundle_platform"),
        Index("ix_atlas_processed_apps_bundle", "bundle_id"),
        Index("ix_atlas_processed_apps_platform", "platform"),
    )
