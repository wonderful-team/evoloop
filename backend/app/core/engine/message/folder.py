"""
MessageNormalizer - 消息规范化工具类

统一处理消息由扁平结构（DB/Dict）向规范化结构（MessageBlock）的转换逻辑。
遵循“即读即显”原则，移除冗余的对象转换层。
"""
import logging
from typing import Any

from app.core.engine.message.factory import MessageBlockFactory
from app.core.engine.message.schemas import MessageBlock

logger = logging.getLogger(__name__)


class MessageNormalizer:
    """
    Utility for normalizing messages into a consistent format.
    Delegates to MessageBlockFactory to ensure structural parity with streaming events.
    """

    @classmethod
    def normalize_dict(cls, msg: Any) -> dict:
        """
        Legacy support for callers expecting a dict.
        Normalizes a single message by mapping it to a MessageBlock and dumping it.
        """
        block = MessageBlockFactory.from_orm(msg)
        return block.model_dump()

    @classmethod
    def normalize(cls, messages: list[Any]) -> list[MessageBlock]:
        """
        Maps a list of raw messages (DB records or dicts) directly to MessageBlock.
        """
        result: list[MessageBlock] = []

        for msg in messages:
            try:
                block = MessageBlockFactory.from_orm(msg)
                result.append(block)
            except (ValueError, TypeError, AttributeError) as e:
                logger.error(f"[MessageNormalizer] Failed to normalize message: {e}")
                # Skip invalid messages to prevent breaking the whole list
                continue

        return result
