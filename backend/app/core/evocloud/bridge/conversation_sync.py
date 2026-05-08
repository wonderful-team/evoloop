# conversation_sync.py - Desktop 对话历史同步到 MC
# 职责: 将本地 SQLite 的 conversations/messages 同步到 Member Center

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.core.evocloud.schemas import SyncConversation, SyncMessage
from app.infrastructure.database.sql.database import get_db_session
from app.models import Conversation as ConversationModel
from app.models import Message as MessageModel

logger = logging.getLogger(__name__)


class ConversationSyncManager:
    """
    对话历史同步管理器

    触发方式:
    1. 事件驱动: AgentRunCompletedEvent 触发后立即执行增量同步
    2. 兜底轮询: 每 30 分钟扫描一次未同步的会话
    3. 全量同步: 首次启动时自动执行（通过 Huey 后台执行）

    同步粒度:
    - 基于 Conversation.sync_status / Message.sync_status 判断差异
    - 增量同步通过 Huey 任务在后台执行，不阻塞主流程
    """

    def __init__(self, api_client, device_key: str):
        self.api = api_client
        self.device_key = device_key
        self._running = False
        self._sync_task: asyncio.Task | None = None
        self._last_sync_time: datetime | None = None

    async def start(self):
        """启动同步管理器"""
        if self._running:
            return

        self._running = True
        logger.info(f"[ConversationSync] Started for device {self.device_key}")

        # 启动后台同步任务
        self._sync_task = asyncio.create_task(self._sync_loop())

        # 提交全量同步任务（不阻塞启动）
        if self.device_key:
            await self._schedule_full_sync()

    async def stop(self):
        """停止同步管理器"""
        self._running = False

        # 取消定时任务
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

        logger.info(f"[ConversationSync] Stopped for device {self.device_key}")

    async def _sync_loop(self):
        """后台同步循环（兜底轮询）"""
        try:
            while self._running:
                await asyncio.sleep(1800)  # 30 分钟兜底轮询

                if not self._running:
                    break

                await self._schedule_incremental_sync()

        except asyncio.CancelledError:
            logger.debug("[ConversationSync] Sync loop cancelled")
        except Exception as e:
            logger.error(f"[ConversationSync] Sync loop error: {e}", exc_info=True)

    async def _schedule_full_sync(self):
        """调度全量同步任务（通过 Huey）"""
        if not self.device_key:
            logger.debug("[ConversationSync] Skip full sync: no device_key")
            return

        try:
            from app.core.evocloud.bridge.sync_tasks import full_sync_task

            async with get_db_session() as db:
                # 获取未同步的会话
                conversations_result = await db.execute(
                    select(ConversationModel).where(ConversationModel.sync_status != 'synced')
                )
                conversations = conversations_result.scalars().all()

                # 获取未同步的消息
                messages_result = await db.execute(
                    select(MessageModel).where(MessageModel.sync_status != 'synced')
                )
                messages = messages_result.scalars().all()

                # 转换数据格式
                conv_data = [self._format_conversation(c).model_dump() for c in conversations]
                msg_data = [self._format_message(m).model_dump() for m in messages]

                # 提交到 Huey
                result = full_sync_task.delay(self.device_key, {
                    "conversations": conv_data,
                    "messages": msg_data,
                })

                logger.info(
                    f"[ConversationSync] Full sync scheduled: "
                    f"{len(conv_data)} conversations, {len(msg_data)} messages "
                    f"task_id={result.id}"
                )

        except Exception as e:
            logger.error(f"[ConversationSync] Failed to schedule full sync: {e}", exc_info=True)

    async def _schedule_incremental_sync(self):
        """调度增量同步任务（通过 Huey）"""
        if not self.device_key:
            logger.debug("[ConversationSync] Skip incremental sync: no device_key")
            return

        try:
            from app.core.evocloud.bridge.sync_tasks import incremental_sync_task

            async with get_db_session() as db:
                # 1. 获取未同步的会话ID
                result = await db.execute(
                    select(ConversationModel.id).where(ConversationModel.sync_status != 'synced')
                )
                pending_thread_ids = {str(r[0]) for r in result.all()}

                # 2. 获取包含未同步消息的会话ID
                msg_result = await db.execute(
                    select(MessageModel.thread_id).where(MessageModel.sync_status != 'synced').distinct()
                )
                msg_thread_ids = {str(r[0]) for r in msg_result.all() if r[0]}

                # 合并（并集）
                thread_ids = list(pending_thread_ids | msg_thread_ids)

                if not thread_ids:
                    return

                # 分批提交（每批100个会话）
                batch_size = 100
                for i in range(0, len(thread_ids), batch_size):
                    batch = thread_ids[i:i + batch_size]
                    result = incremental_sync_task.delay(self.device_key, batch)
                    logger.debug(
                        f"[ConversationSync] Incremental sync batch scheduled: "
                        f"{len(batch)} threads, task_id={result.id}"
                    )

                logger.info(
                    f"[ConversationSync] Incremental sync scheduled: "
                    f"{len(thread_ids)} threads in "
                    f"{(len(thread_ids) + batch_size - 1) // batch_size} batches"
                )

        except Exception as e:
            logger.error(f"[ConversationSync] Failed to schedule incremental sync: {e}", exc_info=True)

    # ==================== 公共 API ====================

    async def full_sync(self):
        """
        手动触发全量同步（公共API）
        注意：实际执行在 Huey Worker 中，不阻塞调用者
        """
        await self._schedule_full_sync()

    async def incremental_sync(self):
        """
        手动触发增量同步（公共API）
        注意：实际执行在 Huey Worker 中，不阻塞调用者
        """
        await self._schedule_incremental_sync()

    # ==================== 数据格式化 ====================

    def _format_conversation(self, conv: ConversationModel) -> SyncConversation:
        """格式化会话数据"""
        return SyncConversation(
            id=str(conv.id),
            project_id=conv.project_id or 0,
            title=conv.title or "新会话",
            created_at=int(conv.created_at.timestamp()) if conv.created_at else int(datetime.now().timestamp()),
            updated_at=int(conv.updated_at.timestamp()) if conv.updated_at else int(datetime.now().timestamp()),
        )

    def _format_message(self, msg: MessageModel) -> SyncMessage:
        """格式化消息数据"""
        return SyncMessage(
            id=msg.id,
            thread_id=msg.thread_id,
            project_id=msg.project_id or 0,
            role=msg.role,
            content=msg.content,
            thinking=msg.thinking,
            created_at=int(msg.created_at.timestamp()) if msg.created_at else int(datetime.now().timestamp()),
            sequence_number=msg.sequence_number or 0,
            checkpoint_id=msg.checkpoint_id or "",
            tool_calls=msg.tool_calls if msg.tool_calls else None,
            action_type=msg.action_type or "text",
            is_visible=1 if msg.is_visible else 0,
            run_id=msg.run_id or "",
            status=msg.status or "completed",
            parent_id=msg.parent_id or 0,
            category=msg.category or "",
            tool_call_id=msg.tool_call_id or "",
            tool_name=msg.tool_name or "",
            meta_data=msg.meta_data,
            content_type=msg.content_type or "text",
        )


# 全局同步管理器实例
_conversation_sync_manager: ConversationSyncManager | None = None


def get_conversation_sync_manager(api_client, device_key: str) -> ConversationSyncManager:
    """获取或创建同步管理器"""
    global _conversation_sync_manager

    if _conversation_sync_manager is None:
        _conversation_sync_manager = ConversationSyncManager(api_client, device_key)

    return _conversation_sync_manager


async def start_conversation_sync(api_client, device_key: str):
    """启动对话历史同步"""
    manager = get_conversation_sync_manager(api_client, device_key)
    await manager.start()
    return manager


async def stop_conversation_sync():
    """停止对话历史同步"""
    global _conversation_sync_manager

    if _conversation_sync_manager:
        await _conversation_sync_manager.stop()
        _conversation_sync_manager = None
