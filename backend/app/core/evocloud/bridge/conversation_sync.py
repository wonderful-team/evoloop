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

    功能:
    1. 实时同步: 新消息产生时立即进入队列，批量提交到 Huey
    2. 定时同步: 每5分钟执行增量同步
    3. 全量同步: 首次启动或手动触发（通过 Huey 后台执行）
    4. 增量同步: 基于 sync_status 检查差异

    架构:
    - 内存队列聚合消息（减少 Huey 任务数量）
    - Huey + SQLite 持久化任务队列
    - 自动重试机制（指数退避）
    """

    def __init__(self, api_client, device_key: str):
        self.api = api_client
        self.device_key = device_key
        self._running = False
        self._sync_task: asyncio.Task | None = None
        self._last_sync_time: datetime | None = None

        # 消息缓冲（用于聚合批量发送）
        self._msg_buffer: list[MessageModel] = []
        self._buffer_lock = asyncio.Lock()
        self._buffer_timer: asyncio.Task | None = None
        self._buffer_flush_interval = 2.0  # 2秒刷新一次
        self._buffer_max_size = 50  # 最大缓冲数量

        # 去重：防止重复同步同一会话
        self._pending_conversations: set[str] = set()

    async def start(self):
        """启动同步管理器"""
        if self._running:
            return

        self._running = True
        logger.info(f"[ConversationSync] Started for device {self.device_key}")

        # 启动后台同步任务
        self._sync_task = asyncio.create_task(self._sync_loop())

        # 启动缓冲刷新任务
        asyncio.create_task(self._buffer_flush_loop())

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

        # 取消缓冲计时器
        if self._buffer_timer:
            self._buffer_timer.cancel()
            try:
                await self._buffer_timer
            except asyncio.CancelledError:
                pass
            self._buffer_timer = None

        # 最后刷新缓冲
        await self._flush_buffer()

        logger.info(f"[ConversationSync] Stopped for device {self.device_key}")

    async def _sync_loop(self):
        """后台同步循环"""
        try:
            while self._running:
                # 每5分钟执行增量同步
                await asyncio.sleep(300)

                if not self._running:
                    break

                await self._schedule_incremental_sync()

        except asyncio.CancelledError:
            logger.debug("[ConversationSync] Sync loop cancelled")
        except Exception as e:
            logger.error(f"[ConversationSync] Sync loop error: {e}", exc_info=True)

    async def _buffer_flush_loop(self):
        """定期刷新缓冲的循环"""
        while self._running:
            try:
                await asyncio.sleep(self._buffer_flush_interval)
                if self._msg_buffer:
                    await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ConversationSync] Buffer flush error: {e}")

    # ==================== 缓冲机制 ====================

    async def _add_to_buffer(self, message: MessageModel):
        """添加消息到缓冲"""
        async with self._buffer_lock:
            self._msg_buffer.append(message)

            # 如果缓冲满了，立即刷新
            if len(self._msg_buffer) >= self._buffer_max_size:
                asyncio.create_task(self._flush_buffer())

    async def _flush_buffer(self):
        """刷新缓冲，提交到 Huey"""
        async with self._buffer_lock:
            if not self._msg_buffer or not self.device_key:
                return

            batch = self._msg_buffer
            self._msg_buffer = []

        if not batch:
            return

        try:
            # 按 thread_id 分组
            groups: dict[str, list[MessageModel]] = {}
            for msg in batch:
                tid = msg.thread_id
                if tid not in groups:
                    groups[tid] = []
                groups[tid].append(msg)

            # 为每个 thread 提交一个 Huey 任务
            from app.core.evocloud.bridge.sync_tasks import sync_messages_task

            for thread_id, messages in groups.items():
                msg_data = [self._format_message(m).model_dump() for m in messages]

                # 提交到 Huey（立即返回，不阻塞）
                result = sync_messages_task.delay(
                    self.device_key,
                    thread_id,
                    msg_data
                )
                logger.debug(
                    f"[ConversationSync] Queued {len(messages)} messages "
                    f"for thread {thread_id}, task_id={result.id}"
                )

        except Exception as e:
            logger.error(f"[ConversationSync] Failed to queue messages: {e}", exc_info=True)

    # ==================== 同步调度 ====================

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
                # 获取未同步的会话ID
                result = await db.execute(
                    select(ConversationModel.id).where(ConversationModel.sync_status != 'synced')
                )
                conversation_ids = [str(r[0]) for r in result.all()]

                if not conversation_ids:
                    return

                # 分批提交（每批100个会话）
                batch_size = 100
                for i in range(0, len(conversation_ids), batch_size):
                    batch = conversation_ids[i:i + batch_size]
                    result = incremental_sync_task.delay(self.device_key, batch)
                    logger.debug(
                        f"[ConversationSync] Incremental sync batch scheduled: "
                        f"{len(batch)} conversations, task_id={result.id}"
                    )

                logger.info(
                    f"[ConversationSync] Incremental sync scheduled: "
                    f"{len(conversation_ids)} conversations in "
                    f"{(len(conversation_ids) + batch_size - 1) // batch_size} batches"
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

    async def sync_conversation(self, conversation: ConversationModel):
        """
        同步单个会话（公共API）
        直接提交到 Huey，不缓冲
        """
        if not self.device_key:
            logger.debug("[ConversationSync] Skip sync_conversation: no device_key")
            return

        # 防止重复提交
        conv_id = str(conversation.id)
        if conv_id in self._pending_conversations:
            return
        self._pending_conversations.add(conv_id)

        try:
            from app.core.evocloud.bridge.sync_tasks import sync_conversation_task

            conv_data = self._format_conversation(conversation).model_dump()
            result = sync_conversation_task.delay(self.device_key, conv_data)

            logger.debug(
                f"[ConversationSync] Conversation sync queued: {conv_id} "
                f"task_id={result.id}"
            )

        except Exception as e:
            logger.error(f"[ConversationSync] Failed to queue conversation: {e}", exc_info=True)
        finally:
            # 延迟移除去重标记（给任务执行时间）
            asyncio.create_task(self._remove_pending_after_delay(conv_id, 30))

    async def sync_messages_batch(self, thread_id: str, messages: list[MessageModel]):
        """
        批量同步消息（公共API）
        添加到缓冲，定期批量提交
        """
        if not messages or not self.device_key:
            return

        for msg in messages:
            await self._add_to_buffer(msg)

    async def on_new_message(self, message: MessageModel):
        """新消息回调 - 实时同步（缓冲）"""
        # Mark message as pending if not set
        if message.sync_status != "pending":
            # We should ideally do this in DB, but MessageModel object passed here
            # might be updated by caller.
            pass

        # When a new message is added, the conversation status should return to 'pending'
        # so it can be picked up by incremental sync if real-time sync fails.
        async with get_db_session() as db:
            from sqlalchemy import update
            await db.execute(
                update(ConversationModel)
                .where(ConversationModel.id == message.thread_id)
                .values(sync_status="pending")
            )
            await db.commit()

        await self._add_to_buffer(message)

    async def on_conversation_updated(self, conversation: ConversationModel):
        """会话更新回调 - 立即同步（不缓冲）"""
        await self.sync_conversation(conversation)

    async def _remove_pending_after_delay(self, conv_id: str, delay: int):
        """延迟移除去重标记"""
        await asyncio.sleep(delay)
        self._pending_conversations.discard(conv_id)

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
            steps_snapshot=msg.steps_snapshot if msg.steps_snapshot else None,
            parent_id=msg.parent_id or 0,
            category=msg.category or "",
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
