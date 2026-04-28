"""
MessagePersistencePolicy - 消息持久化策略

定义不同分类消息的持久化规则：
- 是否入库
- 存储到哪个字段
- 是否记录元数据
"""

import logging

from app.core.engine.message.category import MessageCategory
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.core.engine.message.schemas import PersistencePolicyResult

logger = logging.getLogger(__name__)


class MessagePersistencePolicy:
    """
    消息持久化策略
    
    集中管理所有消息的持久化规则，避免分散在各处的过滤逻辑。
    
    注：持久化规则已下沉到 MessageCategory 枚举本身，此类仅作为统一入口
    和结果封装，避免调用方直接访问枚举内部细节。
    """

    @classmethod
    def should_persist(cls, category: MessageCategory) -> bool:
        """判断消息是否应该持久化到数据库"""
        return category.should_persist_to_db

    @classmethod
    def get_storage_field(cls, category: MessageCategory) -> str | None:
        """获取存储字段（content / thinking / None）"""
        return category.storage_field

    @classmethod
    def should_store_tool_calls(cls, category: MessageCategory) -> bool:
        """判断是否应该存储 tool_calls"""
        return category.should_store_tool_calls

    @classmethod
    def apply_policy(
        cls,
        category: MessageCategory,
        content: str,
        tool_calls: list | None = None,
        thinking: str | None = None,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
    ) -> PersistencePolicyResult:
        """
        应用持久化策略，返回处理后的数据
        
        Args:
            category: 消息分类
            content: 原始内容
            tool_calls: 工具调用列表
            thinking: 思考内容
            tool_call_id: 工具调用 ID
            tool_name: 工具名称
            
        Returns:
            PersistencePolicyResult: 处理后的数据
        """
        should_persist = category.should_persist_to_db
        storage_field = category.storage_field
        should_store_tools = category.should_store_tool_calls

        result = PersistencePolicyResult(
            should_persist=should_persist,
            content=None,
            thinking=None,
            tool_calls=tool_calls if should_store_tools else None,
            category=category.value,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )

        if not should_persist:
            logger.debug(f"[PersistencePolicy] Skipping {category.value} message")
            return result

        # 根据存储字段映射内容
        if storage_field == "content":
            result.content = content
            # 思考内容单独处理（如果有）
            if thinking:
                result.thinking = thinking
        elif storage_field == "thinking":
            # 思考过程存入 thinking 字段
            result.thinking = content
            result.content = ""

        return result

    @classmethod
    def get_all_categories(cls) -> list[MessageCategory]:
        """获取所有支持的分类"""
        return list(MessageCategory)

    @classmethod
    def get_persisted_categories(cls) -> list[MessageCategory]:
        """获取会持久化的分类列表"""
        return [
            cat for cat in MessageCategory
            if cat.should_persist_to_db
        ]
