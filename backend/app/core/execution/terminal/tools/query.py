"""Background task query and cancellation tools."""

import logging
import os
import signal
from typing import Annotated

from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.execution.terminal.background import TaskStatus, task_manager
from app.core.tools.base import InjectedToolArg

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_hidden=True,
    summary_template="evoloop.tool_summary.query_command_status",
)
async def query_command_status(
    task_id: str,
    include_output: bool = True,
    output_lines: int = 50,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    task = task_manager.get_task(task_id)

    if not task:
        return (
            f"Task not found: `{task_id}`\n\n"
            "Possible reasons:\n"
            "1. Wrong task ID\n"
            "2. Task completed over 24 hours ago (auto-cleaned)\n"
            "3. Task belongs to another conversation"
        )

    status_labels = {
        TaskStatus.PENDING: "PENDING",
        TaskStatus.RUNNING: "RUNNING",
        TaskStatus.COMPLETED: "COMPLETED",
        TaskStatus.FAILED: "FAILED",
        TaskStatus.CANCELLED: "CANCELLED",
        TaskStatus.TIMEOUT: "TIMEOUT",
    }
    status_label = status_labels.get(task.status, task.status.value)

    lines = [
        f"Status: {status_label}",
        "",
        f"任务ID: `{task.task_id}`",
        f"命令: `{task.title}`",
        f"耗时: {task.elapsed_seconds}秒",
    ]

    if task.status == TaskStatus.RUNNING:
        lines.append(f"进程ID: {task.process_id}")

    lines.append("")

    if include_output and task.output_buffer:
        n = min(output_lines, 200)
        output = task.get_recent_output(n)
        lines.append(f"最近输出（最后{n}行）:")
        lines.append("```")
        lines.append(output if output else "（无输出）")
        lines.append("```")
        lines.append("")

    if task.status == TaskStatus.COMPLETED:
        lines.append("Command execution successful")
        if task.result:
            lines.append(f"结果: {task.result}")
    elif task.status == TaskStatus.FAILED:
        lines.append(f"Execution failed: {task.error_message or 'unknown error'}")
    elif task.status == TaskStatus.CANCELLED:
        lines.append("Task cancelled")
    elif task.status == TaskStatus.TIMEOUT:
        lines.append("Task timeout")
    elif task.status == TaskStatus.RUNNING:
        lines.append("Note: Task is still running, query again in 10 seconds for latest status")

    return "\n".join(lines)


@evoloop_tool(
    summary_template="evoloop.tool_summary.cancel_command",
)
async def cancel_command(
    task_id: str,
    force: bool = False,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
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
