from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class AtlasApp(Base):
    __tablename__ = "atlas_apps"

    id: Mapped[int] = mapped_column(primary_key=True)
    bundle_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    app_name: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(50), default="macos")
    version_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    states: Mapped[list["AtlasState"]] = relationship(back_populates="app", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "app_name": self.app_name,
            "platform": self.platform,
            "version_hash": self.version_hash,
            "last_observed_at": self.last_observed_at.isoformat() if self.last_observed_at else None,
        }


class AtlasState(Base):
    __tablename__ = "atlas_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("atlas_apps.id"))
    state_id: Mapped[str] = mapped_column(String(255))
    window_title: Mapped[str] = mapped_column(String(512), default="")
    screenshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    elements_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    app: Mapped["AtlasApp"] = relationship(back_populates="states")


class AtlasTransition(Base):
    __tablename__ = "atlas_transitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("atlas_apps.id"))
    from_state_id: Mapped[str] = mapped_column(String(255))
    to_state_id: Mapped[str] = mapped_column(String(255))
    action_label: Mapped[str] = mapped_column(String(255), default="")
    action_type: Mapped[str] = mapped_column(String(50), default="click")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
