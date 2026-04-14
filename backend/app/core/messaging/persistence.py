"""
MessagePersistencePolicy - 消息持久化策略

定义不同分类消息的持久化规则：
- 是否入库
- 存储到哪个字段
- 是否记录元数据
"""

import logging
from typing import Optional

from app.core.messaging.category import MessageCategory

from pydantic import BaseModel, ConfigDict
from app.infrastructure.pydantic_base import DynamicBaseModel

logger = logging.getLogger(__name__)


class PersistencePolicyResult(DynamicBaseModel):
    should_persist: bool
    content: str | None = None
    thinking: str | None = None
    tool_calls: list | None = None
    category: str


class MessagePersistencePolicy:
    """
    消息持久化策略
    
    集中管理所有消息的持久化规则，避免分散在各处的过滤逻辑。
    """
    
    # 分类 → (是否入库, 存储字段, 是否记录 tool_calls)
    _RULES = {
        MessageCategory.USER: (True, "content", False),
        MessageCategory.ASSISTANT_RESPONSE: (True, "content", True),
        MessageCategory.ASSISTANT_TOOL_CALL: (True, "content", True),
        MessageCategory.TOOL_OUTPUT: (True, "content", False),
        MessageCategory.INTERNAL_TOOL_CALL: (False, None, False),
        MessageCategory.INTERNAL_REASONING: (True, "thinking", False),
        MessageCategory.INTERNAL_SYSTEM: (False, None, False),
        MessageCategory.INTERNAL_LLM_JSON: (False, None, False),
        MessageCategory.ERROR_SYSTEM: (False, None, False),  # 系统错误不入库
        MessageCategory.AUTH_EXPIRED: (False, None, False),  # EvoLoop认证过期不入库
        MessageCategory.ERROR_BUSINESS: (True, "content", False),  # 业务错误入库供Agent学习
    }
    
    @classmethod
    def should_persist(cls, category: MessageCategory) -> bool:
        """
        判断消息是否应该持久化到数据库
        
        Args:
            category: 消息分类
            
        Returns:
            bool: 是否入库
        """
        should, _, _ = cls._RULES.get(category, (False, None, False))
        return should
    
    @classmethod
    def get_storage_field(cls, category: MessageCategory) -> Optional[str]:
        """
        获取存储字段
        
        Args:
            category: 消息分类
            
        Returns:
            "content": 存入 content 字段
            "thinking": 存入 thinking 字段
            None: 不存储
        """
        _, field, _ = cls._RULES.get(category, (False, None, False))
        return field
    
    @classmethod
    def should_store_tool_calls(cls, category: MessageCategory) -> bool:
        """
        判断是否应该存储 tool_calls
        
        Args:
            category: 消息分类
            
        Returns:
            bool: 是否存储 tool_calls
        """
        _, _, store_tools = cls._RULES.get(category, (False, None, False))
        return store_tools
    
    @classmethod
    def apply_policy(
        cls,
        category: MessageCategory,
        content: str,
        tool_calls: Optional[list] = None,
        thinking: Optional[str] = None,
    ) -> PersistencePolicyResult:
        """
        应用持久化策略，返回处理后的数据
        
        Args:
            category: 消息分类
            content: 原始内容
            tool_calls: 工具调用列表
            thinking: 思考内容
            
        Returns:
            dict: 包含处理后数据的字典
            {
                "should_persist": bool,
                "content": str | None,
                "thinking": str | None,
                "tool_calls": list | None,
                "category": str,
            }
        """
        should_persist = cls.should_persist(category)
        storage_field = cls.get_storage_field(category)
        should_store_tools = cls.should_store_tool_calls(category)
        
        result = PersistencePolicyResult(
            should_persist=should_persist,
            content=None,
            thinking=None,
            tool_calls=tool_calls if should_store_tools else None,
            category=category.value,
        )
        
        if not should_persist:
            logger.debug(f"[PersistencePolicy] Skipping {category.value} message")
            return result
        
        # 根据存储字段映射内容
        if storage_field == "content":
            result["content"] = content
            # 思考内容单独处理（如果有）
            if thinking:
                result["thinking"] = thinking
        elif storage_field == "thinking":
            # 思考过程存入 thinking 字段
            # content 字段可以为空或保留摘要
            result["thinking"] = content
            result["content"] = ""  # 或生成摘要
        
        return result
    
    @classmethod
    def get_all_categories(cls) -> list[MessageCategory]:
        """获取所有支持的分类"""
        return list(cls._RULES.keys())
    
    @classmethod
    def get_persisted_categories(cls) -> list[MessageCategory]:
        """获取会持久化的分类列表"""
        return [
            cat for cat in cls._RULES.keys()
            if cls.should_persist(cat)
        ]
