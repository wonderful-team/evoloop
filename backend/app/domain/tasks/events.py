from __future__ import annotations

from typing import Any

from app.core.engine.message.broker import get_message_broker
from app.models.project import ProjectTask
from app.utils.time import utcnow


async def publish_workflow_event(
    workflow_id: str,
    *,
    event: str,
    task_id: str | None = None,
    stage: str | None = None,
    status: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "type": "workflow_updated",
        "workflow_id": workflow_id,
        "event": event,
        "at": utcnow().isoformat(),
    }
    if task_id is not None:
        payload["task_id"] = task_id
    if stage is not None:
        payload["stage"] = stage
    if status is not None:
        payload["status"] = status
    if extra:
        payload.update(extra)

    await get_message_broker().publish(
        f"workflow:{workflow_id}:events",
        payload,
    )


async def publish_task_queue_event(
    task: ProjectTask,
    *,
    event: str,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "type": "task_queue_updated",
        "event": event,
        "task_id": task.id,
        "project_id": task.project_id or 0,
        "status": task.status,
        "title": task.title
        if task.title is not None
        else (task.task_data or {}).get("title"),
        "at": utcnow().isoformat(),
    }
    if extra:
        payload.update(extra)

    broker = get_message_broker()
    await broker.publish(f"tasks:{task.project_id or 0}:events", payload)
    await broker.publish("tasks:all:events", payload)


async def publish_queue_drained(
    *, completed: int, failed: int, waiting: int, pending: int
) -> None:
    """值守排空：本轮活动任务全部终态（无 in_progress）——一次性战报。

    前端状态条据此展示"本轮值守完成"汇总（见 AutonomousDutyPage）。
    """
    payload = {
        "type": "queue_drained",
        "event": "queue_drained",
        "completed": completed,
        "failed": failed,
        "waiting": waiting,
        "pending": pending,
        "at": utcnow().isoformat(),
    }
    await get_message_broker().publish("tasks:all:events", payload)
