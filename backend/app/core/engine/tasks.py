import logging
import time

from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.constants import MessageStatus
from app.infrastructure.database import session_scope
from app.infrastructure.queue.factory import shared_task
from app.models import FileOperation, Message

logger = logging.getLogger(__name__)


async def _notify_file_operation(
    thread_id: str, message_id: str, file_path: str, operation: str
):
    """Notify frontend of new file operation via SSE through MessagePublisher."""
    from app.core.engine.message.publisher import MessagePublisher
    from app.core.engine.message.schemas import MessageBlock

    block = MessageBlock(
        id=f"file-op-{thread_id}-{message_id}",
        thread_id=thread_id,
        role="system",
        category=MessageCategory.FILE_OPERATION,
        content=f"File {operation}: {file_path}",
        content_type="text",
        status=MessageStatus.COMPLETED,
        is_visible=False,
        sequence_number=int(time.time() * 1000),
        meta_data={
            "file_path": file_path,
            "operation": operation,
            "message_id": message_id,
        },
    )

    publisher = MessagePublisher(thread_id=thread_id)
    # SSE-only: Celery-side file operation progress is not a persisted chat
    # message and should never be pushed to mobile/voice channels.
    await publisher.publish(block, channels={"sse"})
    logger.debug(f"[Task] Published file operation event for {file_path}")


async def _persist_file_operation(
    thread_id: str,
    message_id: str,
    file_path: str,
    operation: str,
    diff_content: str,
    original_content: str | None = None,
    run_id: str | None = None,
    tool_call_id: str | None = None,
):
    """Internal implementation of file operation persistence."""
    async with session_scope() as session:
        # Determine final message ID (resolve tool_call_id if needed)
        target_msg_id = message_id
        if tool_call_id:
            # Find the actual message ID associated with this tool_call_id
            stmt_msg = (
                select(Message.id)
                .where(
                    Message.thread_id == thread_id, Message.tool_call_id == tool_call_id
                )
                .order_by(desc(Message.sequence_number))
            )
            res = await session.execute(stmt_msg)
            found_id = res.scalar_one_or_none()
            if found_id:
                target_msg_id = found_id

        op = FileOperation(
            thread_id=thread_id,
            message_id=target_msg_id,
            run_id=run_id,
            file_path=file_path,
            operation=operation,
            diff_content=diff_content,
            original_content=original_content,
        )
        session.add(op)
        logger.info(f"[Task] Persisted file operation for {file_path}")

    # --- [Phase 2] 同步到消息标准化引用并触发实时更新 ---
    from app.core.engine.message.repository import MessageRepository

    repo = MessageRepository(thread_id=thread_id)
    await repo.sync_changeset_reference(
        message_id=message_id,
        file_path=file_path,
        operation=operation,
        run_id=run_id,
        tool_call_id=tool_call_id,
        diff_content=diff_content,
    )


async def run_persist_file_operation(
    thread_id: str,
    message_id: str,
    file_path: str,
    operation: str,
    diff_content: str,
    original_content: str | None = None,
    run_id: str | None = None,
    tool_call_id: str | None = None,
):
    """完整文件操作持久化：落库 + SSE 徽章 + 变更集事件。

    供 ``persist_file_operation_task``（Celery/Huey 任务包装）与嵌入式模式
    （``FileChangeTracker`` 进程内确定性调用）共用，保证两条路径功能一致。
    """
    from app.core.engine.message.mapper import BlockMapper
    from app.core.engine.message.publisher import MessagePublisher

    await _persist_file_operation(
        thread_id=thread_id,
        message_id=message_id,
        file_path=file_path,
        operation=operation,
        diff_content=diff_content,
        original_content=original_content,
        run_id=run_id,
        tool_call_id=tool_call_id,
    )

    # 2. 触发 SSE 增量更新：让前端气泡即时显示“变更徽章”
    async with session_scope() as session:
        # 获取最新的消息（带引用）
        stmt = (
            select(Message)
            .where(Message.id == message_id)
            .options(selectinload(Message.references))
        )
        result = await session.execute(stmt)
        db_msg = result.scalar_one_or_none()

        if db_msg:
            block = BlockMapper.from_db(db_msg)
            publisher = MessagePublisher(thread_id=thread_id)
            # SSE-only: this is an incremental "update" refresh for the web
            # message that the user already sees; skip mobile/voice broadcast.
            # action="update" 会触发前端对应消息的局部刷新
            await publisher.publish(block, action="update", channels={"sse"})

    # 原有的细粒度通知逻辑保留
    await _notify_file_operation(thread_id, message_id, file_path, operation)

    # Notify sidebar changeset panel to refresh
    try:
        from app.core.events import system_bus
        from app.core.file.event import ChangesetUpdatedEvent

        await system_bus.publish(
            ChangesetUpdatedEvent(
                thread_id=thread_id,
                message_id=message_id,
                file_path=file_path,
                operation=operation,
            )
        )
    except Exception as e:
        logger.warning(f"[Task] Failed to publish changeset updated event: {e}", exc_info=True)


@shared_task(name="engine_persist_file_operation")
async def persist_file_operation_task(
    thread_id: str,
    message_id: str,
    file_path: str,
    operation: str,
    diff_content: str,
    original_content: str | None = None,
    run_id: str | None = None,
    tool_call_id: str | None = None,
):
    """Background task wrapper。"""
    await run_persist_file_operation(
        thread_id=thread_id,
        message_id=message_id,
        file_path=file_path,
        operation=operation,
        diff_content=diff_content,
        original_content=original_content,
        run_id=run_id,
        tool_call_id=tool_call_id,
    )


@shared_task(name="engine_resume_agent_background")  # type: ignore[reportCallIssue]
async def resume_agent_background_task(
    thread_id: str,
    inputs: dict,
    config: dict,
    run_label: str = "Resuming...",
    clear_human_request_flag: bool = False,
):
    """
    Execute graph resumption in the background (within Celery/Huey worker).
    """
    from app.core.engine.resume_runner import resume_agent_background

    await resume_agent_background(
        thread_id=thread_id,
        inputs=inputs,
        config=config,
        run_label=run_label,
        clear_human_request_flag=clear_human_request_flag,
    )
