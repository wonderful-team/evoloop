"""
Conversation Sync Tasks - Huey-based background sync for EvoCloud.

这些任务使用 Huey + SQLite 进行持久化队列管理，支持：
- 自动重试（指数退避）
- 进程重启后恢复
- 批量处理优化
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.evocloud.schemas import SyncConversation, SyncMessage
from app.infrastructure.database.sql.database import get_db_session
from app.infrastructure.queue.factory import shared_task
from app.models import Conversation as ConversationModel, Message as MessageModel

logger = logging.getLogger(__name__)


@shared_task(
    name="evocloud.sync_full",
    retries=2,
    retry_delay=30,
)
async def full_sync_task(device_key: str, data: dict) -> dict:
    """
    全量同步会话和消息。

    Args:
        device_key: 设备标识
        data: 包含 conversations 和 messages 的字典

    Returns:
        API 响应结果
    """
    from app.core.evocloud import evocloud_manager

    api = evocloud_manager.api

    conversations = data.get("conversations", [])
    messages = data.get("messages", [])

    try:
        # Step 1: Sync all conversations metadata with 'seed' messages
        seed_messages = []
        seed_message_ids = set()

        conv_to_messages = {}
        for msg in messages:
            tid = msg.get("thread_id")
            if tid not in conv_to_messages:
                conv_to_messages[tid] = []
            conv_to_messages[tid].append(msg)

        for conv in conversations:
            cid = conv.get("id")
            thread_msgs = conv_to_messages.get(cid, [])
            if thread_msgs:
                seed = thread_msgs[-1]
                seed_messages.append(seed)
                seed_message_ids.add(seed.get("id"))

        result = await api.sync_full_conversations(device_key, {
            "conversations": conversations,
            "messages": seed_messages,
        })

        if result.get("code") != 0:
            error_msg = result.get("message", "Unknown error")
            logger.error(f"[SyncTask] Metadata sync failed: code={result.get('code')} message={error_msg}")
            if result.get("code") in (-1001, -1002, -1003):
                return result
            raise Exception(f"Metadata sync failed: {error_msg}")

        # Wait for backend to commit the session creation
        logger.info("[SyncTask] Step 1 finished. Waiting 2s for backend consistency...")
        await asyncio.sleep(2.0)

        # Step 2: Sync remaining messages in batches
        valid_conv_ids = {c.get("id") for c in conversations}
        orphaned_thread_ids = set()

        filtered_messages = []
        for m in messages:
            tid = m.get("thread_id")
            if tid in valid_conv_ids:
                if m.get("id") not in seed_message_ids:
                    filtered_messages.append(m)
            else:
                orphaned_thread_ids.add(tid)

        if orphaned_thread_ids:
            logger.warning(
                f"[SyncTask] Skipping {len(messages) - len(filtered_messages) - len(seed_messages)} "
                f"orphaned messages belonging to non-existent sessions: {list(orphaned_thread_ids)}"
            )

        if not filtered_messages:
            logger.info("[SyncTask] No additional messages to sync (after filtering orphans). Full sync completed.")
            return result

        groups: dict[str, list[dict]] = {}
        for msg in filtered_messages:
            tid = msg.get("thread_id")
            if tid not in groups:
                groups[tid] = []
            groups[tid].append(msg)

        total_synced = len(seed_messages)
        batch_size = 100

        for thread_id, thread_messages in groups.items():
            logger.info(f"[SyncTask] Step 2: Syncing {len(thread_messages)} additional messages for thread {thread_id}")

            for i in range(0, len(thread_messages), batch_size):
                chunk = thread_messages[i:i + batch_size]
                chunk_index = (i // batch_size) + 1
                total_chunks = (len(thread_messages) + batch_size - 1) // batch_size

                logger.debug(f"[SyncTask]   -> Sending batch {chunk_index}/{total_chunks} ({len(chunk)} messages)")

                chunk_result = await api.sync_messages(device_key, thread_id, chunk)

                if chunk_result.get("code") != 0:
                    error_msg = chunk_result.get("message", "Unknown error")
                    logger.error(f"[SyncTask] Error syncing message batch for thread {thread_id}: {error_msg}")
                    raise Exception(f"Message batch sync failed: {error_msg}")

                total_synced += len(chunk)

        logger.info(
            f"[SyncTask] Full sync completed successfully: "
            f"{len(conversations)} conversations, {total_synced} messages (including seeds)."
        )

        # Update sync status for everything
        async with get_db_session() as db:
            conv_ids = [c.get("id") for c in conversations if c.get("id")]
            if conv_ids:
                await db.execute(
                    update(ConversationModel)
                    .where(ConversationModel.id.in_(conv_ids))
                    .values(sync_status="synced", last_synced_at=datetime.now(timezone.utc))
                )

            msg_ids = [m.get("id") for m in messages if m.get("id")]
            if msg_ids:
                await db.execute(
                    update(MessageModel)
                    .where(MessageModel.id.in_(msg_ids))
                    .values(sync_status="synced", last_synced_at=datetime.now(timezone.utc))
                )
            await db.commit()

        return {"code": 0, "data": {"conversations": len(conversations), "messages": total_synced}}

    except Exception as e:
        err_str = str(e).lower()
        if any(kw in err_str for kw in ("connect", "unreachable", "timeout", "socket", "network")):
            logger.warning(f"[SyncTask] Cloud unreachable during full sync (device={device_key}). Skipping noisy retry.")
            return {"code": -1, "message": "Cloud unreachable"}

        logger.error(f"[SyncTask] Exception in full sync: {type(e).__name__}: {e}")
        raise


@shared_task(
    name="evocloud.sync_incremental",
    retries=2,
    retry_delay=10,
)
async def incremental_sync_task(device_key: str, conversation_ids: list[str]) -> dict:
    """
    增量同步指定会话。

    Args:
        device_key: 设备标识
        conversation_ids: 需要同步的会话ID列表

    Returns:
        API 响应结果
    """
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

                        api_result = await api.sync_conversation(device_key, conv_data.model_dump())
                        if api_result.get("code") == 0:
                            results["synced"] += 1
                            # Update local sync status
                            await db.execute(
                                update(ConversationModel)
                                .where(ConversationModel.id == conv_id)
                                .values(sync_status="synced", last_synced_at=datetime.now(timezone.utc))
                            )

                            # Also check for unsynced messages in this conversation
                            msg_result = await db.execute(
                                select(MessageModel).where(
                                    MessageModel.thread_id == conv_id,
                                    MessageModel.sync_status != "synced"
                                )
                            )
                            unsynced_msgs = msg_result.scalars().all()
                            if unsynced_msgs:
                                logger.info(f"[SyncTask] Found {len(unsynced_msgs)} unsynced messages in thread {conv_id}")
                                formatted_msgs = []
                                for m in unsynced_msgs:
                                    sm = SyncMessage(
                                        id=m.id, thread_id=m.thread_id, project_id=m.project_id or 0,
                                        role=m.role, content=m.content, thinking=m.thinking,
                                        created_at=int(m.created_at.timestamp()) if m.created_at else 0,
                                        sequence_number=m.sequence_number or 0, category=m.category or ""
                                    )
                                    formatted_msgs.append(sm.model_dump())

                                msg_api_result = await api.sync_messages(device_key, str(conv_id), formatted_msgs)
                                if msg_api_result.get("code") == 0:
                                    await db.execute(
                                        update(MessageModel)
                                        .where(MessageModel.id.in_([m.id for m in unsynced_msgs]))
                                        .values(sync_status="synced", last_synced_at=datetime.now(timezone.utc))
                                    )
                                    logger.info(f"[SyncTask] Synced {len(unsynced_msgs)} backlogged messages for {conv_id}")

                            await db.commit()
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
