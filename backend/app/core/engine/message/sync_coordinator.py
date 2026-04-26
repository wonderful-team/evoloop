"""
MessageSyncCoordinator - 消息同步协调器

职责：
1. 监听消息持久化事件，每 N 条触发一次批量同步
2. 从数据库读取未同步的消息，通过 WebSocket 发送到 Gateway
3. Agent 运行完成后发送最终同步 + 完成信号

使用场景：
- DatabaseCallbackHandler 每处理一批消息后触发
- BackgroundAgent 运行完成后触发最终同步
"""

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from app.core.evocloud import evocloud_manager
from app.infrastructure.database.sql.database import session_scope
from app.models import Conversation, Message

logger = logging.getLogger(__name__)


class MessageSyncCoordinator:
    """协调消息批量同步到 Gateway"""

    def __init__(self, batch_size: int = 5):
        self.batch_size = batch_size
        self._counter = 0
        # per-thread 的同步进度，避免多 conversation 间互相污染
        self._last_synced_seq: dict[str, int] = {}
        # per-thread 的同步锁，防止并发竞争导致重复发送
        self._sync_locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, thread_id: str) -> asyncio.Lock:
        """获取（或创建）指定 thread 的同步锁。"""
        if thread_id not in self._sync_locks:
            self._sync_locks[thread_id] = asyncio.Lock()
        return self._sync_locks[thread_id]



    def reset(self):
        """重置计数器（新任务开始时调用）"""
        self._counter = 0
        self._last_synced_seq.clear()
        self._sync_locks.clear()

    async def on_message_persisted(self, thread_id: str) -> bool:
        """
        消息持久化后的回调。

        每达到 batch_size 条消息，触发一次批量同步。

        Returns:
            bool: 是否触发了同步
        """
        self._counter += 1
        if self._counter % self.batch_size == 0:
            await self.sync_batch(thread_id)
            return True
        return False

    async def sync_batch(self, thread_id: str) -> dict[str, Any] | None:
        """
        同步一批消息到 Gateway。

        增量同步：只读取该 thread _last_synced_seq 之后的新消息，避免全量传输。
        last_synced_seq=0 时查询所有消息（首次同步），之后只查询新增消息。

        使用 per-thread 锁防止并发竞争导致重复发送。
        """
        if not evocloud_manager.link or not evocloud_manager.link.is_connected():
            logger.debug("[SyncCoordinator] WebSocket not connected, skipping sync")
            return None

        async with self._get_lock(thread_id):
            try:
                async with session_scope() as session:
                    # 读取会话元数据
                    conv_result = await session.execute(
                        select(Conversation).where(Conversation.id == thread_id)
                    )
                    conversation = conv_result.scalar_one_or_none()

                    last_seq = self._last_synced_seq.get(thread_id, 0)

                    # 增量读取
                    query = (
                        select(Message)
                        .where(Message.thread_id == thread_id)
                        .order_by(Message.sequence_number.asc())
                    )
                    if last_seq > 0:
                        query = query.where(Message.sequence_number > last_seq)

                    msg_result = await session.execute(query)
                    messages = msg_result.scalars().all()

                    if not messages:
                        logger.debug(
                            f"[SyncCoordinator] No new messages to sync for {thread_id} "
                            f"(last_synced_seq={last_seq})"
                        )
                        return None

                    # 构建同步 payload
                    sync_payload = self._build_sync_payload(conversation, messages)

                    # 通过 WebSocket 发送
                    await evocloud_manager.link.send_message({
                        "type": "message_sync",
                        "data": sync_payload,
                    })

                    new_max_seq = max(m.sequence_number for m in messages)
                    logger.info(
                        f"[SyncCoordinator] Synced batch to Gateway: "
                        f"thread={thread_id}, messages={len(messages)}, "
                        f"seq_range=({last_seq+1 if last_seq > 0 else 1}~{new_max_seq})"
                    )

                    self._last_synced_seq[thread_id] = new_max_seq
                    return sync_payload

            except Exception as e:
                logger.error(f"[SyncCoordinator] Failed to sync batch: {e}")
                return None

    async def sync_final(self, thread_id: str, command_id: str | int | None = None) -> dict[str, Any] | None:
        """
        最终同步：Agent 运行完成后发送完成信号。

        消息同步已由 sync_batch（每条消息触发）实时完成，
        sync_final 只负责发送 command_complete 通知 Mobile Agent 已结束。
        """
        # 发送最终增量同步（补偿运行过程中可能漏掉的消息）
        sync_payload = await self.sync_batch(thread_id)

        # 发送 command_complete
        try:
            if evocloud_manager.link and evocloud_manager.link.is_connected():
                cmd_id = command_id if command_id is not None else 0
                await evocloud_manager.link.send_message({
                    "type": "command_complete",
                    "data": {
                        "thread_id": thread_id,
                        "command_id": cmd_id,
                        "status": "done",
                    },
                })
                logger.info(
                    f"[SyncCoordinator] Sent command_complete: "
                    f"thread={thread_id}, command_id={command_id}"
                )
        except Exception as e:
            logger.error(f"[SyncCoordinator] Failed to send command_complete: {e}")

        return sync_payload

    def _build_sync_payload(
        self,
        conversation: Conversation | None,
        messages: list[Message],
    ) -> dict[str, Any]:
        """构建同步 payload。

        统一协议：Agent → Gateway → Mobile → PHP 使用同一格式，Gateway 只做透明转发。
        payload 中包含 device_key，Gateway 不需要再包装成 SyncPayload。
        """
        from app.core.evocloud.schemas import SyncConversation, SyncMessage
        from app.core.evocloud import evocloud_manager

        # 从 WebSocket Link 获取 device_key，Gateway 不需要再注入
        device_key = evocloud_manager.link.device_key if evocloud_manager.link else ""

        conv_data = None
        if conversation:
            conv_data = SyncConversation(
                id=conversation.id,
                project_id=conversation.project_id or 0,
                title=conversation.title or "新会话",
                created_at=int(conversation.created_at.timestamp()) if conversation.created_at else 0,
                updated_at=int(conversation.updated_at.timestamp()) if conversation.updated_at else 0,
            ).model_dump()

        msg_data = []
        for m in messages:
            msg_data.append(SyncMessage(
                id=str(m.id),
                thread_id=m.thread_id,
                project_id=m.project_id or 0,
                role=m.role,
                content=m.content,
                thinking=m.thinking,
                created_at=int(m.created_at.timestamp()) if m.created_at else 0,
                sequence_number=m.sequence_number or 0,
                checkpoint_id=m.checkpoint_id or "",
                tool_calls=m.tool_calls,
                action_type=m.action_type or "text",
                is_visible=1 if m.is_visible else 0,
                run_id=m.run_id or "",
                status=m.status or "completed",
                steps_snapshot=m.steps_snapshot,
                parent_id=m.parent_id or 0,
                category=m.category or "",
            ).model_dump())

        return {
            "device_key": device_key,
            "sync_type": "incremental",
            "thread_id": conversation.id if conversation else "",
            "conversation": conv_data,
            "messages": msg_data,
        }


# 全局单例
_message_sync_coordinator: MessageSyncCoordinator | None = None


def get_sync_coordinator(batch_size: int = 5) -> MessageSyncCoordinator:
    """获取全局 MessageSyncCoordinator 单例"""
    global _message_sync_coordinator
    if _message_sync_coordinator is None:
        _message_sync_coordinator = MessageSyncCoordinator(batch_size=batch_size)
    return _message_sync_coordinator
