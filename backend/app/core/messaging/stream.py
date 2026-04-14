"""
MessageStreamPolicy - 消息流式推送策略

定义不同分类消息的 SSE/WebSocket 推送规则。
"""

import logging
from typing import Optional

from app.core.messaging.category import MessageCategory
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class StreamPolicyResult(DynamicBaseModel):
    should_stream: bool
    frontend_type: str | None = None
    content: str
    category: str
    metadata: dict = {}


class MessageStreamPolicy:
    """
    消息流式推送策略
    
    集中管理所有消息的实时推送规则。
    """
    
    # 分类 → (是否推送, 前端显示类型)
    _RULES = {
        MessageCategory.USER: (True, "human"),
        MessageCategory.ASSISTANT_RESPONSE: (True, "ai"),
        MessageCategory.ASSISTANT_TOOL_CALL: (True, "ai"),  # 工具调用消息也推送（用于步骤跟踪）
        MessageCategory.TOOL_OUTPUT: (True, "tool"),
        MessageCategory.INTERNAL_TOOL_CALL: (False, None),  # 内部工具调用不推送
        MessageCategory.INTERNAL_REASONING: (True, "thought"),  # 思考过程推送（可选显示）
        MessageCategory.INTERNAL_SYSTEM: (False, None),
        MessageCategory.INTERNAL_LLM_JSON: (False, None),
        MessageCategory.ERROR_SYSTEM: (False, None),  # 系统错误不流式推送
        MessageCategory.AUTH_EXPIRED: (False, None),  # EvoLoop认证过期不流式推送
        MessageCategory.ERROR_BUSINESS: (False, None),  # 业务错误不流式推送
    }
    
    @classmethod
    def should_stream(cls, category: MessageCategory) -> bool:
        """
        判断消息是否应该推送到前端
        
        Args:
            category: 消息分类
            
        Returns:
            bool: 是否推送
        """
        should, _ = cls._RULES.get(category, (False, None))
        return should
    
    @classmethod
    def get_frontend_type(cls, category: MessageCategory) -> Optional[str]:
        """
        获取前端显示类型
        
        Args:
            category: 消息分类
            
        Returns:
            str: 前端类型 (human, ai, tool, thought)
            None: 不推送
        """
        _, frontend_type = cls._RULES.get(category, (False, None))
        return frontend_type
    
    @classmethod
    def apply_policy(
        cls,
        category: MessageCategory,
        content: str,
        metadata: Optional[dict] = None,
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
            cat for cat in cls._RULES.keys()
            if cls.should_stream(cat)
        ]
