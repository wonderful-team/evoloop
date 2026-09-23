"""TaskRun — 任务与运行分离（审计/观测层）。

职责边界（2026-09 任务系统收敛的裁决）：
- ``task_runs`` 只做**过程记录**：每次派发尝试一行（attempt 历史、
  执行线程、终态、失败原因、每轮 token 消耗）。
- **不参与状态机判定**：任务态推进的唯一权威是 ``project_tasks.status``
  + version 乐观锁（TaskQueueService）；reconcile 判死读 AgentActivity。
  run 行只是把"这个任务跑过几轮、每轮结果如何"从单行覆盖态变成可查历史。

写入点（TaskQueueService 内聚，禁止散落）：
- ``claim_for_dispatch`` → 创建 run（running，attempt=dispatch_count）
- ``advance_task`` 成功推进 → run 终态化（succeeded / failed）
- ``requeue_stuck_task`` / ``requeue_workflow_task`` → run 终态化（failed）
- ``release_dispatch_claim``（派发失败回滚）→ run 终态化（failed, 派发失败）
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.sql.database import Base
from app.utils.time import utcnow


class TaskRun(Base):
    """One dispatch attempt of a ProjectTask (process history, not state authority)."""

    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    # 任务内第几次尝试（与 task.dispatch_count 同源递增）
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    # claimed / running / succeeded / failed / cancelled / timed_out
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 每轮 token 消耗（run 收尾时从 AgentActivity 抄录）：{input, output, llm_calls}
    tokens: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
