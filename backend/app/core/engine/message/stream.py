"""
MessageStreamPolicy - 消息流式推送策略

定义不同分类消息的 SSE/WebSocket 推送规则。
"""

import logging

from app.core.engine.message.category import MessageCategory
from app.core.engine.message.schemas import StreamPolicyResult

logger = logging.getLogger(__name__)


class MessageStreamPolicy:
    """
    消息流式推送策略
    
    集中管理所有消息的实时推送规则。
    所有规则已下沉到 MessageCategory 枚举属性，此类仅作为统一入口。
    """

    @classmethod
    def should_stream(cls, category: MessageCategory) -> bool:
        """
        判断消息是否应该推送到前端
        
        Args:
            category: 消息分类
            
        Returns:
            bool: 是否推送
        """
        return category.should_stream_to_frontend

    @classmethod
    def get_frontend_type(cls, category: MessageCategory) -> str | None:
        """
        获取前端显示类型
        
        Args:
            category: 消息分类
            
        Returns:
            str: 前端类型 (human, ai, tool, thought)
            None: 不推送
        """
        return category.frontend_type

    @classmethod
    def apply_policy(
        cls,
        category: MessageCategory,
        content: str,
        metadata: dict | None = None,
    ) -> StreamPolicyResult:
        """
        应用流式推送策略
        
        Args:
            category: 消息分类
            content: 消息内容
            metadata: 元数据
            
        Returns:
            dict: 包含推送决策的字典
            {
                "should_stream": bool,
                "frontend_type": str | None,
                "content": str,  # 可能经过处理的内容
            }
        """
        should_stream = cls.should_stream(category)
        frontend_type = cls.get_frontend_type(category)

        if not should_stream:
            logger.debug(f"[StreamPolicy] Not streaming {category.value} message")

        return StreamPolicyResult(
            should_stream=should_stream,
            frontend_type=frontend_type,
            content=content,
            category=category.value,
            metadata=metadata or {},
        )

    @classmethod
    def get_streamed_categories(cls) -> list[MessageCategory]:
        """获取会推送到前端的分类列表"""
        return [
            cat for cat in MessageCategory
            if cls.should_stream(cat)
        ]
