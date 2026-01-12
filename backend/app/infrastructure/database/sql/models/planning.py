from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    thread_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, completed, archived
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="plan")
    steps: Mapped[list["PlanStep"]] = relationship(back_populates="plan", cascade="all, delete-orphan", order_by="PlanStep.order")


class PlanStep(Base):
    __tablename__ = "plan_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, in_progress, completed, failed
    result: Mapped[str | None] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Phase 8: Deep Linking
    execution_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # ID of the run that executed this step

    plan: Mapped["Plan"] = relationship(back_populates="steps")
