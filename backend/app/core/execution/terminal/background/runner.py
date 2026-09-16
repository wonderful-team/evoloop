"""Background command execution — long-running task management."""

import asyncio
import logging

from app.constants import DEFAULT_PROJECT_ID
from app.core.context import ContextManager
from app.core.engine.message.native_classes import RunnableConfig
from app.core.execution.constants import (
    DEFAULT_OUTPUT_LINES,
    MAX_COMMAND_TITLE_LENGTH,
    QUICK_TIMEOUT_SECONDS,
)
from app.core.execution.sandbox.factory import SandboxFactory
from app.core.execution.terminal.background import (
    CreateBackgroundTaskRequest,
    TaskType,
    task_manager,
)
from app.core.execution.terminal.background.utils import (
    format_command_result,
    get_thread_id,
)
from app.core.project.utils import get_project_path, get_workspace_root
from app.core.security.command import has_workspace_escape, is_dangerous_command
from app.core.security.path import get_allowed_roots
from app.core.tools import get_working_directory

logger = logging.getLogger(__name__)

_WORKSPACE_ESCAPE_ERROR = (
    "Security Error: 命令尝试访问允许的工作目录之外，"
    "已在沙箱内阻止。请在当前工作目录或其允许的子目录内操作。"
)


def _build_allowed_roots(working_dir: str | None, project_path: str | None = None) -> list[str]:
    """Build the list of directories commands are allowed to access.

    Delegates to the centralized path security helper so that execute_command,
    file tools, and hooks all agree on the safe boundaries. 传入 project_path
    （项目会话激活）时边界收敛为项目作用域——WORKSPACE_ROOT 不再整体放行。
    """
    return get_allowed_roots(working_dir=working_dir, project_path=project_path)


def _member_id_for(config: RunnableConfig | None) -> int:
    """从当前执行上下文解析归属会员（沙箱按用户隔离需要）。

    仅读 ctx.member_id（dispatch/build_ctx 链路已保证写入）；缺失返回 0，
    工厂侧 fail-closed 拒绝——不在执行热路径里做 DB 回查。
    """
    from app.core.config import settings as _settings

    if not _settings.MULTI_TENANT_MODE:
        return 0
    ctx = ContextManager.current()
    mid = getattr(ctx, "member_id", None) or 0
    try:
        return int(mid) if mid else 0
    except (TypeError, ValueError):
        return 0


async def _resolve_working_dir(command: str, config: RunnableConfig | None) -> tuple[str | None, str | None]:
    """Resolve the working directory and run policy checks.

    Returns ``(working_dir, security_error|None)``. When ``security_error`` is
    set the command must not run.
    """
    ctx = ContextManager.current()
    working_dir = get_working_directory(config)

    project_path: str | None = None
    if ctx.project_id and ctx.project_id != DEFAULT_PROJECT_ID:
        # 项目会话：解析项目本地路径，cd 逃逸检查按项目作用域收窄边界
        # （复用 get_project_path 单一解析出处，不走平行实现）。
        project_path = await get_project_path(ctx.project_id) or None

    if ctx.project_id == DEFAULT_PROJECT_ID or (
        ctx.project_id is None and working_dir == "."
    ):
        # 多租户：默认工作目录锁定为“该 member 的工作根”
        # （全局 WORKSPACE_ROOT 在多租户下是所有用户目录的父目录，
        #  绝不能用作成员的默认 cwd；也避免 wrapper cd 越界被误拦）。
        from app.core.config import settings as _settings

        if _settings.MULTI_TENANT_MODE:
            from app.core.project.utils import (
                current_member_id,
                resolve_member_workspace_root,
            )

            member_root = resolve_member_workspace_root(current_member_id())
            if member_root:
                working_dir = member_root
            else:
                return None, (
                    "Security Error: member workspace unavailable in multi-tenant mode"
                )
        else:
            workspace_root = get_workspace_root()
            if workspace_root:
                working_dir = workspace_root

    is_dangerous, reason = is_dangerous_command(command)
    if is_dangerous:
        return None, f"Security Error: {reason}"

    if working_dir and working_dir != ".":
        allowed_roots = _build_allowed_roots(working_dir, project_path)
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
            return None, _WORKSPACE_ESCAPE_ERROR

    return working_dir or None, None


async def _create_execution_task(command: str, thread_id: str, timeout: int):
    return await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title=f"执行: {command[:MAX_COMMAND_TITLE_LENGTH]}{'...' if len(command) > MAX_COMMAND_TITLE_LENGTH else ''}",
            description=f"命令: {command}",
            tool_name="bash",
            thread_id=thread_id,
            timeout_seconds=timeout,
            metadata={"enable_streaming_output": True},
        )
    )


async def _finalize_task(task_id: str, exit_code: int) -> None:
    if exit_code == 0:
        await task_manager.complete_task(task_id, result={"exit_code": 0})
    else:
        await task_manager.fail_task(
            task_id, error=f"Command exited with code {exit_code}"
        )


async def execute_in_background(command: str, timeout: int, config: RunnableConfig | None) -> str:
    thread_id = get_thread_id(config)

    is_dangerous, reason = is_dangerous_command(command)
    if is_dangerous:
        return f"Security Error: {reason}"

    task = await _create_execution_task(command, thread_id, timeout)

    asyncio.create_task(run_command_background(task, command, timeout, config))

    return (
        "Background task started\n\n"
        f"任务ID: `{task.task_id}`\n"
        f"命令: `{command}`\n"
        f"超时: {timeout}秒\n\n"
        f"查询状态: `query_command_status('{task.task_id}')`\n"
        f"取消任务: `cancel_command('{task.task_id}')`"
    )


async def run_command_background(task, command: str, timeout: int, config: RunnableConfig | None):
    try:
        working_dir, error_msg = await _resolve_working_dir(command, config)
        if error_msg:
            task.append_output(error_msg)
            await task_manager.fail_task(task.task_id, error=error_msg)
            return

        sandbox = await SandboxFactory.get_sandbox(_member_id_for(config))
        process = await sandbox.spawn(
            command,
            working_dir=working_dir,
            on_output=lambda text: task_manager.append_output(task.task_id, text),
        )
        await task_manager.start_task(task.task_id, process.pid)
        task.set_cancel_callback(process.terminate)

        try:
            exit_code = await process.wait(timeout)
            await _finalize_task(task.task_id, exit_code)
        except asyncio.TimeoutError:
            process.kill()
            await task_manager.timeout_task(task.task_id)

    except Exception as e:
        logger.error(f"Background command error: {e}", exc_info=True)
        await task_manager.fail_task(task.task_id, error=str(e))


async def execute_smart(command: str, timeout: int, config: RunnableConfig | None) -> str:
    thread_id = get_thread_id(config)
    quick_timeout = min(timeout, QUICK_TIMEOUT_SECONDS)

    is_dangerous, reason = is_dangerous_command(command)
    if is_dangerous:
        return f"Security Error: {reason}"

    task = await _create_execution_task(command, thread_id, timeout)

    working_dir, error_msg = await _resolve_working_dir(command, config)
    if error_msg:
        return error_msg

    stdout_buf: list[str] = []
    stderr_buf: list[str] = []
    sandbox = await SandboxFactory.get_sandbox(_member_id_for(config))
    process = await sandbox.spawn(
        command,
        working_dir=working_dir,
        on_output=lambda text: task_manager.append_output(task.task_id, text),
        stdout_buf=stdout_buf,
        stderr_buf=stderr_buf,
    )
    await task_manager.start_task(task.task_id, process.pid)
    task.set_cancel_callback(process.terminate)

    try:
        exit_code = await process.wait(quick_timeout)
        await _finalize_task(task.task_id, exit_code)
        return format_command_result(
            "".join(stdout_buf),
            "".join(stderr_buf),
            exit_code,
        )
    except asyncio.TimeoutError:
        if timeout <= quick_timeout:
            process.kill()
            await task_manager.timeout_task(task.task_id)
            return (
                f"Command execution timeout ({quick_timeout}s)\n\n"
                f"命令: `{command}`\n\n"
                f"建议: 此命令可能需要更长时间，请使用后台模式:\n"
                f"`bash(command='{command}', background=True, timeout=300)`"
            )

        async def wait_remaining():
            try:
                exit_code = await process.wait(timeout - quick_timeout)
                await _finalize_task(task.task_id, exit_code)
            except asyncio.TimeoutError:
                process.kill()
                await task_manager.timeout_task(task.task_id)

        asyncio.create_task(wait_remaining())

        output = task.get_recent_output(n=DEFAULT_OUTPUT_LINES)
        return (
            f"Command continues running in background (exceeded quick timeout {quick_timeout}s)\n\n"
            f"任务ID: `{task.task_id}`\n\n"
            f"当前输出:\n```\n{output}```\n\n"
            f"查询完整状态: `query_command_status('{task.task_id}')`"
        )
