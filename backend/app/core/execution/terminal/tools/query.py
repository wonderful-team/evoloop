"""Background task cancellation tool."""

import logging
import os
import signal
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.execution.terminal.background import task_manager
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg

logger = logging.getLogger(__name__)


@evoloop_tool(
    summary_template="evoloop.tool_summary.cancel_command",
)
async def cancel_command(
    task_id: str,
    force: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,  # noqa: ARG001
) -> str:
    task = task_manager.get_task(task_id)

    if not task:
        return f"Task not found: `{task_id}`"

    if task.is_completed:
        return (
            "Task already completed, cannot cancel\n\n"
            f"状态: {task.status.value}\n"
            f"完成时间: {task.completed_at}"
        )

    success = await task_manager.cancel_task(task_id)

    if success:
        if force and task.process_id:
            try:
                os.killpg(os.getpgid(task.process_id), signal.SIGKILL)
            except ProcessLookupError:
                pass

        return f"Task cancelled\n\n任务ID: `{task_id}`\n命令: `{task.title}`"
    else:
        return f"Cannot cancel task (current status: {task.status.value})"
