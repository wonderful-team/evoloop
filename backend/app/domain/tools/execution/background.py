"""Background command execution — long-running task management."""

import asyncio
import logging
import os
import signal

from app.constants import DEFAULT_PROJECT_ID
from app.core.context import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.core.project.utils import get_workspace_root
from app.core.security.command import has_workspace_escape, is_dangerous_command
from app.core.security.path import get_allowed_roots
from app.core.tools import get_working_directory
from app.core.tools.background import CreateBackgroundTaskRequest, TaskType, task_manager
from app.domain.tools.execution._utils import format_command_result, get_thread_id

logger = logging.getLogger(__name__)


def _build_allowed_roots(working_dir: str | None) -> list[str]:
    """Build the list of directories commands are allowed to access.

    Delegates to the centralized path security helper so that execute_command,
    file tools, and hooks all agree on the safe boundaries.
    """
    return get_allowed_roots(working_dir=working_dir)


def _terminate_process_group(process: asyncio.subprocess.Process) -> None:
    """Gracefully terminate the whole process group of a subprocess."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass


async def execute_in_background(
    command: str,
    timeout: int,
    config: RunnableConfig | None,
) -> str:
    thread_id = get_thread_id(config)

    task = await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title=f"执行: {command[:60]}{'...' if len(command) > 60 else ''}",
            description=f"命令: {command}",
            tool_name="execute_command",
            thread_id=thread_id,
            timeout_seconds=timeout,
            metadata={"enable_streaming_output": True},
        )
    )

    asyncio.create_task(run_command_background(task, command, timeout, config))

    return (
        "Background task started\n\n"
        f"任务ID: `{task.task_id}`\n"
        f"命令: `{command}`\n"
        f"超时: {timeout}秒\n\n"
        f"查询状态: `query_command_status('{task.task_id}')`\n"
        f"取消任务: `cancel_command('{task.task_id}')`"
    )


async def run_command_background(
    task,
    command: str,
    timeout: int,
    config: RunnableConfig | None,
):
    try:
        ctx = ContextManager.current()
        working_dir = get_working_directory(config)

        if ctx.project_id == DEFAULT_PROJECT_ID or (
            ctx.project_id is None and working_dir == "."
        ):
            workspace_root = get_workspace_root()
            if workspace_root:
                working_dir = workspace_root

        if working_dir and working_dir != ".":
            allowed_roots = _build_allowed_roots(working_dir)
            escape = has_workspace_escape(
                command,
                working_dir=working_dir,
                allowed_roots=allowed_roots,
            )
            if escape is not None:
                logger.warning(
                    "[execute] blocked workspace escape via cd: %r (working_dir=%s, allowed=%s)",
                    escape,
                    working_dir,
                    allowed_roots,
                )
                task.output_lines = [
                    "Security Error: 命令尝试访问允许的工作目录之外，"
                    "已在沙箱内阻止。请在当前工作目录或其允许的子目录内操作。"
                ]
                task.status = "failed"
                return
            wrapped_command = f"cd {working_dir} && {command}"
        else:
            wrapped_command = command

        process = await asyncio.create_subprocess_shell(
            wrapped_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        await task_manager.start_task(task.task_id, process.pid)

        task.set_cancel_callback(lambda: _terminate_process_group(process))

        async def read_stream(stream, is_stderr=False):
            prefix = "[stderr] " if is_stderr else ""
            while True:
                try:
                    line = await asyncio.wait_for(stream.readline(), timeout=1.0)
                    if not line:
                        break
                    output = prefix + line.decode("utf-8", errors="replace").rstrip()
                    task_manager.append_output(task.task_id, output)
                except asyncio.TimeoutError:
                    if process.returncode is not None:
                        break
                    continue

        await asyncio.gather(
            read_stream(process.stdout, is_stderr=False),
            read_stream(process.stderr, is_stderr=True),
        )

        try:
            exit_code = await asyncio.wait_for(process.wait(), timeout=timeout)

            if exit_code == 0:
                await task_manager.complete_task(task.task_id, result={"exit_code": 0})
            else:
                await task_manager.fail_task(
                    task.task_id,
                    error=f"Command exited with code {exit_code}",
                )
        except asyncio.TimeoutError:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            await task_manager.timeout_task(task.task_id)

    except Exception as e:
        logger.error(f"Background command error: {e}", exc_info=True)
        await task_manager.fail_task(task.task_id, error=str(e))


async def execute_smart(
    command: str,
    timeout: int,
    config: RunnableConfig | None,
) -> str:
    thread_id = get_thread_id(config)
    quick_timeout = min(timeout, 60)

    is_dangerous, reason = is_dangerous_command(command)
    if is_dangerous:
        return f"Security Error: {reason}"

    task = await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title=f"执行: {command[:60]}{'...' if len(command) > 60 else ''}",
            description=f"命令: {command}",
            tool_name="execute_command",
            thread_id=thread_id,
            timeout_seconds=timeout,
            metadata={"enable_streaming_output": True},
        )
    )

    ctx = ContextManager.current()
    working_dir = get_working_directory(config)

    if ctx.project_id == DEFAULT_PROJECT_ID or (
        ctx.project_id is None and working_dir == "."
    ):
        workspace_root = get_workspace_root()
        if workspace_root:
            working_dir = workspace_root

    if working_dir and working_dir != ".":
        allowed_roots = _build_allowed_roots(working_dir)
        escape = has_workspace_escape(
            command,
            working_dir=working_dir,
            allowed_roots=allowed_roots,
        )
        if escape is not None:
            logger.warning(
                "[execute] blocked workspace escape via cd: %r (working_dir=%s, allowed=%s)",
                escape,
                working_dir,
                allowed_roots,
            )
            return (
                "Security Error: 命令尝试访问允许的工作目录之外，"
                "已在沙箱内阻止。请在当前工作目录或其允许的子目录内操作。"
            )
        wrapped_command = f"cd {working_dir} && {command}"
    else:
        wrapped_command = command

    process = await asyncio.create_subprocess_shell(
        wrapped_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=os.setsid,
    )

    await task_manager.start_task(task.task_id, process.pid)

    task.set_cancel_callback(lambda: _terminate_process_group(process))

    stdout_buf = []
    stderr_buf = []

    async def read_stream(stream, is_stderr=False):
        prefix = "[stderr] " if is_stderr else ""
        while True:
            try:
                line = await asyncio.wait_for(stream.readline(), timeout=0.5)
                if not line:
                    break
                decoded_line = line.decode("utf-8", errors="replace")
                if is_stderr:
                    stderr_buf.append(decoded_line)
                else:
                    stdout_buf.append(decoded_line)

                output = prefix + decoded_line.rstrip()
                task_manager.append_output(task.task_id, output + "\n")
            except asyncio.TimeoutError:
                if process.returncode is not None:
                    break
                continue

    async def gather_streams():
        await asyncio.gather(
            read_stream(process.stdout, is_stderr=False),
            read_stream(process.stderr, is_stderr=True),
        )

    read_task = asyncio.create_task(gather_streams())

    try:
        await asyncio.wait_for(asyncio.shield(read_task), timeout=quick_timeout)
        exit_code = await asyncio.wait_for(process.wait(), timeout=1.0)

        if exit_code == 0:
            await task_manager.complete_task(task.task_id, result={"exit_code": 0})
        else:
            await task_manager.fail_task(task.task_id, error=f"Exit code: {exit_code}")

        stdout_str = "".join(stdout_buf)
        stderr_str = "".join(stderr_buf)
        return format_command_result(stdout_str, stderr_str, exit_code, command=command)

    except asyncio.TimeoutError:
        if timeout <= quick_timeout:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            await task_manager.timeout_task(task.task_id)
            return (
                f"Command execution timeout ({quick_timeout}s)\n\n"
                f"命令: `{command}`\n\n"
                f"建议: 此命令可能需要更长时间，请使用后台模式:\n"
                f"`execute_command(command='{command}', background=True, timeout=300)`"
            )

        async def wait_remaining():
            try:
                remaining = timeout - quick_timeout
                await asyncio.wait_for(read_task, timeout=remaining)
                exit_code = await asyncio.wait_for(process.wait(), timeout=5.0)
                if exit_code == 0:
                    await task_manager.complete_task(
                        task.task_id, result={"exit_code": 0}
                    )
                else:
                    await task_manager.fail_task(
                        task.task_id, error=f"Exit code: {exit_code}"
                    )
            except asyncio.TimeoutError:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await task_manager.timeout_task(task.task_id)

        asyncio.create_task(wait_remaining())

        output = task.get_recent_output(n=50)
        return (
            f"Command continues running in background (exceeded quick timeout {quick_timeout}s)\n\n"
            f"任务ID: `{task.task_id}`\n\n"
            f"当前输出:\n```\n{output}```\n\n"
            f"查询完整状态: `query_command_status('{task.task_id}')`"
        )
