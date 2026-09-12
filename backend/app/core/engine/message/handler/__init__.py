"""
MessageHandler - 消息处理器（Orchestrator）

整合分类、持久化、推送策略的统一入口。
替代原来分散在各 callback 中的处理逻辑。

职责拆分：
- MessageClassifier: 分类（纯函数，已存在）
- MessageRepository: 数据库操作（repository.py）
- MessageDeduplicator: 去重（deduplicator.py）
- MessagePublisher: 推送（publisher.py）
- MessageHandler: 编排器（此文件）
"""

import time

from app.core.engine.message.deduplicator import MessageDeduplicator
from app.core.engine.message.handler.ai_mixin import AiMessageMixin
from app.core.engine.message.handler.dispatch_mixin import DispatchMixin
from app.core.engine.message.handler.stream_mixin import StreamMixin
from app.core.engine.message.handler.tool_mixin import ToolMessageMixin
from app.core.engine.message.handler.user_mixin import UserMessageMixin
from app.core.engine.message.publisher import MessagePublisher
from app.core.engine.message.repository import MessageRepository
from app.core.engine.message.schemas import MessageHandlerResult


class MessageHandler(
    AiMessageMixin,
    ToolMessageMixin,
    UserMessageMixin,
    DispatchMixin,
    StreamMixin,
):
    def __init__(
        self,
        thread_id: str,
        project_id: int | None = None,
        run_id: str | None = None,
        member_id: int = 0,
    ):
        self.thread_id = thread_id
        self.project_id = project_id
        self.run_id = run_id
        self.member_id = member_id
        self._publisher: MessagePublisher | None = None
        self._stream_seq = int(time.time() * 1000)

        self.last_persisted_message_id: str | None = None
        self.last_persisted_sequence: int = 0

        self._repository = MessageRepository(thread_id, project_id, run_id, member_id)
        self._deduplicator = MessageDeduplicator()


__all__ = ["MessageHandler", "MessageHandlerResult"]
