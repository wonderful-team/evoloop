"""
Conversation Sync Tasks - Huey-based background sync for EvoCloud.

这些任务使用 Huey + SQLite 进行持久化队列管理，支持：
- 自动重试（指数退避）
- 进程重启后恢复
- 批量处理优化
"""

import logging

from app.core.evocloud.schemas import SyncConversation
from app.infrastructure.queue.factory import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="evocloud.sync_conversation",
    retries=3,
    retry_delay=10,
)
async def sync_conversation_task(device_id: int, conversation: dict) -> dict:
    """
    同步单个会话到 Member Center。

    Args:
        device_id: 设备ID
        conversation: 会话数据字典

    Returns:
        API 响应结果

    Raises:
        Exception: 同步失败时会触发重试
    """
    from app.core.evocloud import evocloud_manager

    api = evocloud_manager.api

    try:
        result = await api.sync_conversation(device_id, conversation)

        if result.get("code") == 0:
            logger.info(
                f"[SyncTask] Conversation synced: {conversation.get('id')} "
                f"device={device_id}"
            )
            return result
        else:
            error_msg = result.get("message", "Unknown error")
            logger.error(
                f"[SyncTask] Failed to sync conversation {conversation.get('id')}: "
                f"code={result.get('code')} message={error_msg}"
            )
            # 业务错误，不重试（通过检查 code 判断）
            if result.get("code") in (-1001, -1002, -1003):  # 认证/权限错误
                logger.warning(f"[SyncTask] Auth error, skipping retry")
                return result
            raise Exception(f"Sync failed: {error_msg}")

    except Exception as e:
        logger.error(
            f"[SyncTask] Exception syncing conversation {conversation.get('id')}: "
            f"{type(e).__name__}: {e}"
        )
        raise


@shared_task(
    name="evocloud.sync_messages",
    retries=3,
    retry_delay=5,
)
async def sync_messages_task(
    device_id: int,
    thread_id: str,
    messages: list[dict]
) -> dict:
    """
    批量同步消息到 Member Center。

    Args:
        device_id: 设备ID
        thread_id: 会话线程ID
        messages: 消息数据列表

    Returns:
        API 响应结果
    """
    from app.core.evocloud import evocloud_manager

    if not messages:
        return {"code": 0, "data": {"inserted_count": 0}}

    api = evocloud_manager.api

    try:
        result = await api.sync_messages(device_id, thread_id, messages)

        if result.get("code") == 0:
            logger.info(
                f"[SyncTask] Messages synced: {len(messages)} messages "
                f"thread={thread_id} device={device_id}"
            )
            return result
        else:
            error_msg = result.get("message", "Unknown error")
            logger.error(
                f"[SyncTask] Failed to sync messages for thread {thread_id}: "
                f"code={result.get('code')} message={error_msg}"
            )
            # 认证错误不重试
            if result.get("code") in (-1001, -1002, -1003):
                return result
            raise Exception(f"Sync failed: {error_msg}")

    except Exception as e:
        logger.error(
            f"[SyncTask] Exception syncing messages for thread {thread_id}: "
            f"{type(e).__name__}: {e}"
        )
        raise


@shared_task(
    name="evocloud.sync_full",
    retries=2,
    retry_delay=30,
)
async def full_sync_task(device_id: int, data: dict) -> dict:
    """
    全量同步会话和消息。

    Args:
        device_id: 设备ID
        data: 包含 conversations 和 messages 的字典

    Returns:
        API 响应结果
    """
    from app.core.evocloud import evocloud_manager

    api = evocloud_manager.api

    conversations = data.get("conversations", [])
    messages = data.get("messages", [])

    try:
        result = await api.sync_full_conversations(device_id, {
            "conversations": conversations,
            "messages": messages,
        })

        if result.get("code") == 0:
            sync_result = result.get("data", {})
            logger.info(
                f"[SyncTask] Full sync completed: "
                f"{sync_result.get('conversations', 0)} conversations, "
                f"{sync_result.get('messages', 0)} messages "
                f"device={device_id}"
            )
            return result
        else:
            error_msg = result.get("message", "Unknown error")
            logger.error(
                f"[SyncTask] Full sync failed: "
                f"code={result.get('code')} message={error_msg}"
            )
            if result.get("code") in (-1001, -1002, -1003):
                return result
            raise Exception(f"Full sync failed: {error_msg}")

    except Exception as e:
        logger.error(
            f"[SyncTask] Exception in full sync: "
            f"{type(e).__name__}: {e}"
        )
        raise


@shared_task(
    name="evocloud.sync_incremental",
    retries=2,
    retry_delay=10,
)
async def incremental_sync_task(device_id: int, conversation_ids: list[str]) -> dict:
    """
    增量同步指定会话。

    Args:
        device_id: 设备ID
        conversation_ids: 需要同步的会话ID列表

    Returns:
        API 响应结果
    """
    from sqlalchemy import select
    from app.infrastructure.database.sql.database import get_db_session
    from app.models import Conversation as ConversationModel
    from app.core.evocloud import evocloud_manager

    api = evocloud_manager.api
    results = {"synced": 0, "failed": 0}

    try:
        async with get_db_session() as db:
            for conv_id in conversation_ids:
                try:
                    result = await db.execute(
                        select(ConversationModel).where(
                            ConversationModel.id == conv_id
                        )
                    )
                    conv = result.scalar_one_or_none()

                    if conv:
                        conv_data = SyncConversation(
                            id=str(conv.id),
                            project_id=conv.project_id or 0,
                            title=conv.title or "新会话",
                            created_at=int(conv.created_at.timestamp()) if conv.created_at else 0,
                            updated_at=int(conv.updated_at.timestamp()) if conv.updated_at else 0,
                        )

                        api_result = await api.sync_conversation(device_id, conv_data.model_dump())
                        if api_result.get("code") == 0:
                            results["synced"] += 1
                        else:
                            results["failed"] += 1
                            logger.warning(
                                f"[SyncTask] Failed to sync conversation {conv_id}: "
                                f"{api_result.get('message')}"
                            )

                except Exception as e:
                    results["failed"] += 1
                    logger.error(f"[SyncTask] Error syncing conversation {conv_id}: {e}")

        logger.info(
            f"[SyncTask] Incremental sync completed: "
            f"{results['synced']} synced, {results['failed']} failed"
        )
        return {"code": 0, "data": results}

    except Exception as e:
        logger.error(f"[SyncTask] Exception in incremental sync: {e}")
        raise
