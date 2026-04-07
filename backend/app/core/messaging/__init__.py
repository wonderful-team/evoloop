"""
EvoLoop Messaging System - 统一消息处理系统

提供消息分类、持久化和推送的完整解决方案。

使用示例：
    from app.core.messaging import (
        MessageCategory,
        MessageClassifier,
        MessagePersistencePolicy,
        MessageStreamPolicy,
        MessageHandler,
    )
    
    # 处理 AI 消息
    handler = MessageHandler(thread_id="xxx", project_id=1)
    result = await handler.handle_ai_message(
        content="我来帮您处理",
        tool_calls=[{"name": "read_file", ...}],
    )
    
    # 分类结果
    category = result["category"]  # "assistant_response" 等
    persisted = result["persisted"]  # True/False
    streamed = result["streamed"]  # True/False
"""

from app.core.messaging.category import MessageCategory
from app.core.messaging.classifier import MessageClassifier
from app.core.messaging.persistence import MessagePersistencePolicy
from app.core.messaging.stream import MessageStreamPolicy
from app.core.messaging.handler import MessageHandler

__all__ = [
    "MessageCategory",
    "MessageClassifier",
    "MessagePersistencePolicy",
    "MessageStreamPolicy",
    "MessageHandler",
]
