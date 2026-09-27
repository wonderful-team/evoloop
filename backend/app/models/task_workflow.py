from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class TaskWorkflow(Base):
    """A business workflow whose stages are dispatched as ProjectTask rows.

    触发/编排/执行三分离（2026-09-25 轮次化收敛）：
    - 触发（什么时候）→ 本表的 trigger_spec/next_run_at（从任务上移：
      recurring 只驱动任务自身的旧语义不足以表达"周期流水线"）；
    - 编排（每轮做什么、顺序、交接）→ 本表 stages 模板（通用路径存
      inputs.stage_template；growth 固定流水线仍走 roles.py）；
    - 执行（怎么干）→ 每轮 spawn 的阶段 ProjectTask（workflow_round 标轮）。
    round_no 是已实例化的最大轮次；轮次实例以
    dedup_key="wf:{workflow_id}:{round}:{stage_key}" 幂等。
    """

    __tablename__ = "task_workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    member_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    title: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str] = mapped_column(Text)
    workflow_type: Mapped[str] = mapped_column(
        String(64), default="commerce_growth_text"
    )
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # 周期触发器（cron 或 "interval:秒"）；非空 = 周期工作流（每轮自动实例化）
    trigger_spec: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 下轮触发时刻（armed/轮次收口后由 calculate_next_run 推进）
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # 已实例化的最大轮次（0 = 尚未开跑）
    round_no: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TaskArtifact(Base):
    """Structured handoff between workflow stages."""

    __tablename__ = "task_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    workflow_id: Mapped[str] = mapped_column(String(36), index=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    stage: Mapped[str] = mapped_column(String(64), index=True)
    artifact_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="generated", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
