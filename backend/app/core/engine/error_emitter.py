"""ErrorEmitter — 错误呈现单出口。

任何层（session 主循环、dispatch、通道处理）捕获到需要告知用户的异常，
一律经 ``error_emitter.emit()`` 发布，禁止各自实现「分类→事件→呈现」。

契约（tests/unit/core/engine/test_error_emitter.py 锁定）：

======================================  ==============================
错误分类（LLMErrorHandler / Inference）  呈现事件
======================================  ==============================
quota_exhausted（含订阅过期）            QuotaExhaustedEvent（续费横幅）
llm_auth                                LLMAuthErrorEvent（toast+设置）
其余（限流/超时/网络/未知）              system 错误消息块（SSE-only）
======================================  ==============================

历史教训：错误路径曾是 6+ 个散落出口（error_mixin 死代码、session 兜底、
各通道自建），导致「后端报错、前端没反应」反复复发。新增错误类型只需：
分类器加关键词 + 契约测试加参数，呈现链路自动继承。
"""

from __future__ import annotations

import logging

from app.core.engine.error_handler import LLMErrorHandler
from app.core.engine.message.constants import MessageContentType, MessageRole
from app.core.engine.message.publisher import MessagePublisher
from app.core.engine.message.schemas import MessageBlock
from app.core.exceptions import InferenceError
from app.models.schemas.events import (
    AuthExpiredEvent,
    LLMAuthErrorEvent,
    QuotaExhaustedEvent,
)
from app.utils.id import unique_id

logger = logging.getLogger(__name__)


class ErrorEmitter:
    """将异常转换为用户可见呈现事件的唯一出口。"""

    async def emit(
        self,
        thread_id: str,
        error: Exception,
        *,
        project_id: int | None = None,
    ) -> None:
        """分类 error 并发布对应呈现事件。自身失败仅记录，不上抛。"""
        try:
            if isinstance(error, InferenceError):
                # InferenceError 已在 LLM 调用边界完成分类，直接复用
                error_type = error.error_type
                title = error_type.replace("_", " ").title()
                message = error.user_friendly_msg
                hint = None
            else:
                classification = LLMErrorHandler.classify_exception(error)
                error_type = classification.error_type
                title = classification.title
                message = classification.message
                hint = classification.hint

            publisher = MessagePublisher(thread_id=thread_id, project_id=project_id)

            if error_type == "auth_expired":
                await publisher.publish(
                    AuthExpiredEvent(
                        thread_id=thread_id,
                        title=title,
                        message=message,
                        hint=hint,
                    )
                )
            elif error_type == "quota_exhausted":
                await publisher.publish(
                    QuotaExhaustedEvent(
                        thread_id=thread_id,
                        title=title,
                        message=message,
                        hint=hint or "",
                    )
                )
            elif error_type == "llm_auth":
                await publisher.publish(
                    LLMAuthErrorEvent(
                        thread_id=thread_id,
                        title=title,
                        message=message,
                    )
                )
            else:
                # 错误消息块（v3.1 路线图：落库 + SSE）——此前 SSE-only，
                # 崩溃后历史无法追溯。先 persist（错误详情不进
                # mobile/voice 通道的决策不变），SSE 块复用同一 id 以便
                # 前端按 id 合并（实时块与历史恢复不重复）。
                block_id = unique_id("err", thread_id)
                content = f"**{title}**\n{message}"
                try:
                    from app.core.context.manager import ContextManager

                    try:
                        member_id = ContextManager.current().member_id or 0
                    except Exception:
                        member_id = 0
                    from app.core.engine.message.repository import MessageRepository

                    repo = MessageRepository(
                        thread_id, project_id, member_id=member_id
                    )
                    await repo.persist(
                        role=MessageRole.SYSTEM,
                        content=content,
                        category="error",
                        is_visible=True,
                        content_type=MessageContentType.TEXT,
                        message_id=block_id,
                    )
                except Exception:
                    # 落库失败不阻断实时呈现（降级为仅 SSE）
                    logger.warning(
                        "[ErrorEmitter] persist error block failed for %s",
                        thread_id,
                        exc_info=True,
                    )
                await publisher.publish(
                    MessageBlock(
                        id=block_id,
                        thread_id=thread_id,
                        role=MessageRole.SYSTEM,
                        content=content,
                        content_type=MessageContentType.TEXT,
                        category="error",
                    ),
                    channels={"sse"},
                )
        except Exception:
            # 崩溃兜底路径必须自身安全：发布失败只记录，不上抛
            logger.exception(
                "[ErrorEmitter] publish failed for thread %s (%s)",
                thread_id,
                type(error).__name__,
            )


error_emitter = ErrorEmitter()
