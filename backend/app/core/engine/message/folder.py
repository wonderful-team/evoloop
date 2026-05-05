"""
MessageNormalizer - 消息规范化工具类

统一处理消息由扁平结构（DB/Dict）向规范化结构（MessageBlock）的转换逻辑。
遵循“即读即显”原则，移除冗余的 LangChain 对象转换层。
"""
import logging
from typing import Any

from app.core.engine.message.schemas import MessageBlock
from app.core.engine.message.factory import MessageBlockFactory
from app.core.tools.registry import get_tool_metadata

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
            # 1. Early filtering for hidden tools (optimization)
            role = MessageBlockFactory._get_val(msg, "role")
            if role == "tool":
                tool_name = MessageBlockFactory._get_val(msg, "tool_name")
                tool_meta = get_tool_metadata(tool_name) if tool_name else None
                if tool_meta and tool_meta.is_hidden:
                    continue

            # 2. Use unified factory to build the block
            try:
                block = MessageBlockFactory.from_orm(msg)
                
                # Filter AI tool_calls that are hidden (already handled partially in factory, but let's be sure)
                # Factory already filters them, so we just append
                result.append(block)
            except Exception as e:
                logger.error(f"[MessageNormalizer] Failed to normalize message: {e}")
                # Skip invalid messages to prevent breaking the whole list
                continue

        return result
