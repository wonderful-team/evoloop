"""
MobileErrorNotifier — 统一错误消息推送到 Mobile 的封装。

将原来分散在 handler.py / errors.py / background_agent/__init__.py 中的
Mobile 推送逻辑集中到此，避免重复实现和遗漏。
"""
import logging

from sqlalchemy import select, func

from app.infrastructure.database.sql.database import session_scope
from app.models import Message

logger = logging.getLogger(__name__)


class MobileErrorNotifier:
    """
    统一错误消息推送到 Mobile。

    使用方式：
        notifier = MobileErrorNotifier(handler)
        await notifier.push(classification)

    其中 classification 是 LLMErrorHandler.classify_exception() 的返回结果。
    """

    def __init__(self, handler):
        self._handler = handler

    async def push(self, classification) -> None:
        """
        推送已分类的错误到 Mobile（自动获取序列号）。

        Args:
            classification: LLMErrorHandler.classify_exception() 的结果
        """
        if not self._handler:
            return

        try:
            seq = await self._next_sequence()
            error_plain = f"{classification.title}\n\n{classification.message}"
            await self._handler._push_to_mobile(
                role="ai",
                content=f"请求失败: {error_plain}",
                category="error_business",
                status="failed",
                sequence_number=seq,
            )
        except Exception as e:
            logger.warning(f"[MobileErrorNotifier] Failed to push error to mobile: {e}")

    async def _next_sequence(self) -> int:
        """从数据库获取下一个序列号（并发安全）。

        Uses SequenceService for atomic counter-based generation.
        Fallback: 如果数据库不可用，使用负时间戳偏移来避免
        与正常序列号冲突（正常序列号从 1 开始递增）。
        """
        try:
            from app.core.engine.message.sequence import SequenceService
            return await SequenceService.next_sequence(self._handler.thread_id)
        except Exception as e:
            logger.warning(f"[MobileErrorNotifier] Failed to get sequence number, using fallback: {e}")
            import time
            # Negative offset from a large base to avoid collision with normal sequences
            return -int(time.time())
