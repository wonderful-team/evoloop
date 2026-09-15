"""Autonomous task queue domain."""

from app.domain.tasks import event  # noqa: F401 — 导入触发 @event_register 注册
from app.domain.tasks.service import TaskQueueError, TaskQueueService

__all__ = ["TaskQueueError", "TaskQueueService"]
