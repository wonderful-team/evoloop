"""
MessageSyncCoordinator - Agent 完成信号发送器

职责：Agent 运行完成后发送 command_complete 信号到 Gateway。

注意：消息同步已改为即时推送（_push_to_mobile()），
此模块不再负责批量消息同步，仅保留完成信号功能。
"""

import logging

from app.core.evocloud import evocloud_manager

logger = logging.getLogger(__name__)


class MessageSyncCoordinator:
    """仅负责发送 Agent 运行完成信号"""

    async def sync_final(self, thread_id: str, command_id: str | int | None = None, status: str = "done") -> None:
        """
        Agent 运行完成信号：发送 command_complete，不附带消息数据。

        消息已在 Agent 运行过程中通过 _push_to_mobile() 即时推送到 Mobile，
        此处仅表示"本轮处理已结束"，并携带最终状态（done/failed/cancelled）。

        Args:
            thread_id: 对话线程 ID
            command_id: 指令 ID
            status: 最终状态 ("done" | "failed" | "cancelled")
        """
        try:
            if evocloud_manager.link and evocloud_manager.link.is_connected():
                cmd_id = command_id if command_id is not None else 0
                await evocloud_manager.link.send_message({
                    "type": "command_complete",
                    "data": {
                        "thread_id": thread_id,
                        "command_id": cmd_id,
                        "status": status,
                    },
                })
                logger.info(f"[SyncCoordinator] Sent command_complete: thread={thread_id}, command_id={command_id}, status={status}")
        except Exception as e:
            logger.error(f"[SyncCoordinator] Failed to send command_complete: {e}")


# 全局单例
_message_sync_coordinator: MessageSyncCoordinator | None = None


def get_sync_coordinator() -> MessageSyncCoordinator:
    """获取全局 MessageSyncCoordinator 单例"""
    global _message_sync_coordinator
    if _message_sync_coordinator is None:
        _message_sync_coordinator = MessageSyncCoordinator()
    return _message_sync_coordinator
