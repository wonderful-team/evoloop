# conversation_sync.py - Desktop 对话历史同步到 MC
# 职责: 将本地 SQLite 的 conversations/messages 同步到 Member Center

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from app.infrastructure.database.sql.database import get_db_session
from app.models import Conversation as ConversationModel, Message as MessageModel

logger = logging.getLogger(__name__)


class ConversationSyncManager:
    """
    对话历史同步管理器
    
    功能:
    1. 实时同步: 新消息产生时立即同步
    2. 定时同步: 每5分钟同步会话元数据
    3. 全量同步: 首次启动或手动触发
    4. 增量同步: 基于 sync_status 检查差异
    """
    
    def __init__(self, api_client, device_key: str, device_id: int = 0):
        self.api = api_client
        self.device_key = device_key
        self.device_id = device_id
        self._running = False
        self._sync_task: asyncio.Task | None = None
        self._last_sync_time: datetime | None = None
        
    async def start(self):
        """启动同步管理器"""
        if self._running:
            return
        
        self._running = True
        logger.info(f"[ConversationSync] Started for device {self.device_key}")
        
        # 确保 device_id 有效 (如果为0，尝试从MC获取)
        await self._ensure_device_id()
        
        # 启动后台同步任务
        self._sync_task = asyncio.create_task(self._sync_loop())
    
    async def _ensure_device_id(self):
        """确保 device_id 有效，如果为0则尝试从MC或manager获取"""
        # First try to get from manager (if already fetched by manager)
        if self.device_id <= 0:
            try:
                from app.core.evocloud import evocloud_manager
                manager_device_id = evocloud_manager.device_id
                if manager_device_id:
                    self.device_id = manager_device_id
                    logger.info(f"[ConversationSync] Got device_id from manager: {self.device_id}")
            except Exception:
                pass
        
        # If still not available, fetch from MC directly
        if self.device_id > 0:
            return
        
        try:
            # 从MC获取设备列表，找到匹配的device_key
            result = await self.api.get_devices()
            if result.get("code") == 0:
                devices = result.get("data", {}).get("list", [])
                for device in devices:
                    if device.get("device_key") == self.device_key:
                        self.device_id = device.get("device_id", 0)
                        logger.info(f"[ConversationSync] Got device_id from MC: {self.device_id}")
                        break
            
            if self.device_id == 0:
                logger.warning(f"[ConversationSync] Could not find device_id for key {self.device_key}, sync will be skipped")
        except Exception as e:
            logger.error(f"[ConversationSync] Failed to get device_id: {e}")
        
    async def stop(self):
        """停止同步管理器"""
        self._running = False
        
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None
        
        logger.info(f"[ConversationSync] Stopped for device {self.device_key}")
        
    async def _sync_loop(self):
        """后台同步循环"""
        try:
            # 首次全量同步
            await self.full_sync()
            
            while self._running:
                # 每5分钟执行增量同步
                await asyncio.sleep(300)
                
                if not self._running:
                    break
                    
                await self.incremental_sync()
                
        except asyncio.CancelledError:
            logger.debug("[ConversationSync] Sync loop cancelled")
        except Exception as e:
            logger.error(f"[ConversationSync] Sync loop error: {e}")
            
    async def full_sync(self):
        """全量同步 - 首次启动或重建时使用"""
        if self.device_id <= 0:
            logger.debug("[ConversationSync] Skip full sync: no device_id")
            return
        
        logger.info("[ConversationSync] Starting full sync...")
        
        try:
            async with get_db_session() as db:
                # 获取所有会话
                conversations_result = await db.execute(
                    ConversationModel.__table__.select()
                )
                conversations = conversations_result.scalars().all()
                
                # 获取所有消息
                messages_result = await db.execute(
                    MessageModel.__table__.select()
                )
                messages = messages_result.scalars().all()
                
                # 转换数据格式
                conv_data = [self._format_conversation(c) for c in conversations]
                msg_data = [self._format_message(m) for m in messages]
                
                # 上报到 MC
                result = await self.api.sync_full_conversations(
                    device_id=self.device_id,
                    data={
                        "conversations": conv_data,
                        "messages": msg_data,
                    }
                )
                
                if result.get("code") == 0:
                    self._last_sync_time = datetime.now()
                    logger.info(
                        f"[ConversationSync] Full sync completed: "
                        f"{result.get('data', {}).get('conversations', 0)} conversations, "
                        f"{result.get('data', {}).get('messages', 0)} messages"
                    )
                else:
                    logger.error(f"[ConversationSync] Full sync failed: {result.get('message')}")
                    
        except Exception as e:
            logger.error(f"[ConversationSync] Full sync error: {e}")
            
    async def incremental_sync(self):
        """增量同步 - 只同步上次同步后更新的数据"""
        if self.device_id <= 0:
            logger.debug("[ConversationSync] Skip incremental sync: no device_id")
            return
        
        if not self._last_sync_time:
            # 如果从未同步过，执行全量同步
            await self.full_sync()
            return
            
        logger.debug("[ConversationSync] Starting incremental sync...")
        
        try:
            # 获取上次同步以来更新的会话
            async with get_db_session() as db:
                # 获取更新的会话
                conversations_result = await db.execute(
                    ConversationModel.__table__.select().where(
                        ConversationModel.updated_at >= self._last_sync_time
                    )
                )
                conversations = conversations_result.scalars().all()
                
                # 同步每个会话
                for conv in conversations:
                    await self.sync_conversation(conv)
                    
                if conversations:
                    logger.info(f"[ConversationSync] Incremental sync: {len(conversations)} conversations")
                    
                self._last_sync_time = datetime.now()
                
        except Exception as e:
            logger.error(f"[ConversationSync] Incremental sync error: {e}")
            
    async def sync_conversation(self, conversation: ConversationModel):
        """同步单个会话"""
        if self.device_id <= 0:
            logger.debug("[ConversationSync] Skip sync_conversation: no device_id")
            return
        
        try:
            conv_data = self._format_conversation(conversation)
            
            result = await self.api.sync_conversation(
                device_id=self.device_id,
                conversation=conv_data
            )
            
            if result.get("code") == 0:
                logger.debug(f"[ConversationSync] Synced conversation: {conversation.id}")
            else:
                logger.warning(f"[ConversationSync] Failed to sync conversation {conversation.id}: {result.get('message')}")
                
        except Exception as e:
            logger.error(f"[ConversationSync] Sync conversation error: {e}")
            
    async def sync_messages_batch(self, thread_id: str, messages: list[MessageModel]):
        """批量同步消息"""
        if not messages:
            return
        
        if self.device_id <= 0:
            logger.debug("[ConversationSync] Skip sync_messages_batch: no device_id")
            return
        
        try:
            msg_data = [self._format_message(m) for m in messages]
            
            result = await self.api.sync_messages(
                device_id=self.device_id,
                thread_id=thread_id,
                messages=msg_data
            )
            
            if result.get("code") == 0:
                logger.debug(
                    f"[ConversationSync] Synced {len(messages)} messages for thread {thread_id}"
                )
            else:
                logger.warning(f"[ConversationSync] Failed to sync messages: {result.get('message')}")
                
        except Exception as e:
            logger.error(f"[ConversationSync] Sync messages error: {e}")
            
    async def on_new_message(self, message: MessageModel):
        """新消息回调 - 实时同步"""
        # 立即同步单条消息
        await self.sync_messages_batch(message.thread_id, [message])
        
    async def on_conversation_updated(self, conversation: ConversationModel):
        """会话更新回调 - 实时同步"""
        await self.sync_conversation(conversation)
        
    def _format_conversation(self, conv: ConversationModel) -> dict:
        """格式化会话数据"""
        return {
            "id": str(conv.id),
            "project_id": conv.project_id or 0,
            "title": conv.title or "新会话",
            "created_at": int(conv.created_at.timestamp()) if conv.created_at else int(datetime.now().timestamp()),
            "updated_at": int(conv.updated_at.timestamp()) if conv.updated_at else int(datetime.now().timestamp()),
        }
        
    def _format_message(self, msg: MessageModel) -> dict:
        """格式化消息数据"""
        return {
            "id": msg.id,
            "thread_id": msg.thread_id,
            "project_id": msg.project_id or 0,
            "role": msg.role,
            "content": msg.content,
            "thinking": msg.thinking,
            "created_at": int(msg.created_at.timestamp()) if msg.created_at else int(datetime.now().timestamp()),
            "sequence_number": msg.sequence_number or 0,
            "checkpoint_id": msg.checkpoint_id or "",
            "tool_calls": json.loads(msg.tool_calls) if msg.tool_calls else None,
            "action_type": msg.action_type or "text",
            "is_visible": 1 if msg.is_visible else 0,
            "run_id": msg.run_id or "",
            "status": msg.status or "completed",
            "steps_snapshot": json.loads(msg.steps_snapshot) if msg.steps_snapshot else None,
            "parent_id": msg.parent_id or 0,
            "category": msg.category or "",
        }


# 全局同步管理器实例
_conversation_sync_manager: ConversationSyncManager | None = None


def get_conversation_sync_manager(api_client, device_key: str, device_id: int = 0) -> ConversationSyncManager:
    """获取或创建同步管理器"""
    global _conversation_sync_manager
    
    if _conversation_sync_manager is None:
        _conversation_sync_manager = ConversationSyncManager(api_client, device_key, device_id)
        
    return _conversation_sync_manager


async def start_conversation_sync(api_client, device_key: str, device_id: int = 0):
    """启动对话历史同步"""
    manager = get_conversation_sync_manager(api_client, device_key, device_id)
    await manager.start()
    return manager


async def stop_conversation_sync():
    """停止对话历史同步"""
    global _conversation_sync_manager
    
    if _conversation_sync_manager:
        await _conversation_sync_manager.stop()
        _conversation_sync_manager = None
