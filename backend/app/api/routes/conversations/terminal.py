import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.context.manager import ContextManager, EvoContext
from app.core.execution.terminal.background import (
    CreateBackgroundTaskRequest,
    TaskType,
    task_manager,
)
from app.core.execution.terminal.manager import terminal_manager
from app.infrastructure.database import session_scope
from app.models import Conversation

router = APIRouter()

logger = logging.getLogger(__name__)


class TerminalCommandRequest(BaseModel):
    command: str
    project_id: int | None = None


class TerminalInputRequest(BaseModel):
    text: str
    project_id: int | None = None


class TerminalCancelRequest(BaseModel):
    task_id: str
    project_id: int | None = None


async def _hydrate_thread_working_directory(thread_id: str, project_id: int | None = None):
    from app.core.context.thread_store import thread_context_store
    from app.core.project.utils import get_project_path

    if project_id is None:
        project_id = thread_context_store.get_active_project(thread_id)

    if project_id is None:
        async with session_scope() as db:
            conv = await db.get(Conversation, thread_id)
            if conv and conv.project_id is not None:
                project_id = conv.project_id

    if project_id is not None:
        thread_context_store.set_active_project(thread_id, project_id)
        project_path = await get_project_path(project_id)
        if project_path:
            thread_context_store.set_working_directory(thread_id, project_path)


@router.post("/{thread_id}/terminal/execute")
async def run_terminal_command(thread_id: str, req: TerminalCommandRequest):
    command = req.command.strip()
    if not command:
        raise HTTPException(status_code=422, detail="command must not be empty")

    await _hydrate_thread_working_directory(thread_id, req.project_id)

    task = await task_manager.create_task(
        CreateBackgroundTaskRequest(
            task_type=TaskType.COMMAND,
            title=command,
            tool_name="user_terminal",
            thread_id=thread_id,
            metadata={"enable_streaming_output": True},
        )
    )

    async def _run_async():
        await task_manager.start_task(task.task_id)
        await task_manager.append_output_async(task.task_id, f"\r\n$ {command}\r\n")

        loop = asyncio.get_running_loop()

        def _blocking_run():
            def on_output(text: str):
                loop.call_soon_threadsafe(task_manager.append_output, task.task_id, text)

            with ContextManager.use(EvoContext(thread_id=thread_id)):
                _, _, exit_code = terminal_manager.run_command(command, on_output=on_output)
            return exit_code

        try:
            exit_code = await loop.run_in_executor(None, _blocking_run)
        except Exception as exc:
            logger.exception(f"[Terminal][{thread_id}] Command execution error")
            await task_manager.fail_task(task.task_id, error=str(exc))
            return

        if exit_code == 0:
            await task_manager.complete_task(task.task_id)
        else:
            await task_manager.fail_task(task.task_id, error=f"Exited with code {exit_code}")

    asyncio.create_task(_run_async())
    return {"task_id": task.task_id}


@router.post("/{thread_id}/terminal/input")
async def send_terminal_input(thread_id: str, req: TerminalInputRequest):
    await _hydrate_thread_working_directory(thread_id, req.project_id)

    session = terminal_manager.get_session_for_thread(thread_id)
    if session is None or session.pty is None:
        with ContextManager.use(EvoContext(thread_id=thread_id)):
            session = terminal_manager.get_session()
            _ = session.get_pty(thread_id)

    pty_inst = session.pty
    if pty_inst is None or pty_inst._master_fd == -1:
        raise HTTPException(
            status_code=400,
            detail="Terminal session not initialised for this thread",
        )

    try:
        pty_inst.write_raw(req.text.encode("utf-8", errors="replace"))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"PTY write failed: {exc}") from exc

    return {"status": "ok"}


@router.post("/{thread_id}/terminal/cancel")
async def cancel_terminal_command(thread_id: str, req: TerminalCancelRequest):
    """取消一个正在执行的终端后台命令。

    终端指令通过 PTY 在常驻 shell 中以前台任务方式运行，
    无法直接 terminate 子进程，因此写入 Ctrl+C (\\x03) 中断前台命令，
    再将其标记为 cancelled。
    """
    await _hydrate_thread_working_directory(thread_id, req.project_id)

    cancelled = await task_manager.cancel_task(req.task_id)

    session = terminal_manager.get_session_for_thread(thread_id)
    pty_inst = session.pty if session is not None else None
    if pty_inst is not None and pty_inst._master_fd != -1:
        try:
            pty_inst.write_raw(b"\x03")
        except OSError as exc:
            logger.warning(
                f"[Terminal][{thread_id}] PTY cancel write failed: {exc}", exc_info=True
            )

    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail=f"Task {req.task_id} not found or already completed",
        )

    return {"status": "cancelled"}


@router.get("/{thread_id}/tasks/active")
async def get_active_thread_tasks(thread_id: str):
    tasks = task_manager.get_active_tasks(thread_id=thread_id)
    return [
        {
            "task_id": t.task_id,
            "task_type": t.task_type.value,
            "title": t.title,
            "status": t.status.value,
            "created_at": t.created_at.isoformat(),
            "output": t.get_recent_output(1000),
            "metadata": t.metadata.model_dump(),
        } for t in tasks
    ]
