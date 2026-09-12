"""Retry 共享服务：web /chat/retry 与 EngineCommand 重派的统一实现。

收敛此前两处重复的「定位目标消息 → rewind → 重派 → submit」逻辑：
  - web /chat/retry（HTTP 入口）
  - EngineCommand rewind+redispatch（桌面端引擎命令）

重派统一走 dispatch_user_message 门面（skip_l0=True：文本入口不执行本地宏；
is_retry + skip_message_persistence 经 channel_kwargs 透传），保证与普通
/chat 同等质量的 intent_hint / host_context / session submit 语义。

语义变化记录：
  - EngineCommand 旧路径的 metadata goal_prefix（"Retry: "）不再保留——
    重派即用户消息重发，goal 前缀是旧图架构残留。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.engine.rewind import (
    MessageNotFoundError,
    NoHumanMessageError,
    RewindError,
    perform_rewind,
)
from app.core.routing.dispatch_handler import dispatch_user_message
from app.core.routing.thread_locks import route_lock_scope

logger = logging.getLogger(__name__)


class RetryError(Exception):
    """Retry 流程错误（message 面向调用方，status 供 HTTP 层映射）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class RetryOutcome:
    ok: bool
    message_id: str | None = None
    target_message_id: str | None = None
    content: str | None = None
    files_reverted: int = 0
    removed_message_count: int = 0
    rewind_errors: list[str] | None = None


async def _locate_target_message(session, thread_id: str, target_message_id: str | None):
    from app.models import Message

    if target_message_id:
        result = await session.execute(
            select(Message)
            .options(selectinload(Message.references))
            .where(Message.id == target_message_id)
        )
        target = result.scalar_one_or_none()
        if not target:
            raise RetryError(f"Message {target_message_id} not found in database", status=404)
        if target.thread_id != thread_id:
            raise RetryError(f"Message {target_message_id} not found in thread", status=404)
        if target.role != "human":
            raise RetryError(f"Message {target_message_id} is not a human message", status=404)
        return target

    result = await session.execute(
        select(Message)
        .options(selectinload(Message.references))
        .where(Message.thread_id == thread_id)
        .where(Message.role == "human")
        .order_by(Message.id.desc())
        .limit(1)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise RetryError("No human message found to retry", status=404)
    return target


def _collect_references(target_msg) -> list[dict] | None:
    if not target_msg.references:
        return None
    return [
        {
            "type": ref.type,
            "id": ref.target_id,
            "target_id": ref.target_id,
            "target_name": ref.target_name,
            "meta_data": ref.meta_data,
        }
        for ref in target_msg.references
    ]


def _restore_host_context(target_msg, explicit: dict | None) -> dict | None:
    """host_context 恢复：显式传入 > 目标消息持久化的 meta_data（原始快照）。"""
    if isinstance(explicit, dict) and explicit:
        return explicit
    meta = target_msg.meta_data or {}
    raw = meta.get("host_context")
    return raw if isinstance(raw, dict) and raw else None


async def retry_and_redispatch(
    *,
    thread_id: str,
    project_id: int,
    context,
    member_id: int = 0,
    target_message_id: str | None = None,
    message_text: str | None = None,
    host_context: dict | None = None,
    revert_files: bool = False,
    reset_state: bool = True,
    include_target: bool = False,
    reason: str = "retry",
    command_id: str | int | None = None,
    model: str | None = None,
    source: str = "web",
) -> RetryOutcome:
    """定位目标 human 消息 → rewind → 统一门面重派 → session submit。

    调用方需已将 ``context`` 设置为当前 EvoContext（ContextManager.set）。
    路由锁由本服务内部持有。
    """
    from app.core.channel.input.web_input import web_input
    from app.core.engine.dispatch import DispatchStatus
    from app.infrastructure.database import session_scope

    # 1. 定位目标消息 + 内容/引用/host_context 恢复
    async with session_scope() as session:
        target_msg = await _locate_target_message(session, thread_id, target_message_id)
        content = message_text if message_text is not None else target_msg.content
        references = _collect_references(target_msg)
        host_ctx = _restore_host_context(target_msg, host_context)
        if target_msg.project_id is not None:
            project_id = target_msg.project_id
        target_message_id = str(target_msg.id)

    # 2. Rewind（删除目标之后的执行痕迹）
    try:
        rewind_result = await perform_rewind(
            thread_id=thread_id,
            target_message_id=target_message_id,
            include_target=include_target,
            revert_files=revert_files,
            reset_state=reset_state,
            reason=reason,
        )
    except MessageNotFoundError as e:
        raise RetryError(f"Target message not found for retry: {e}", status=404) from e
    except NoHumanMessageError as e:
        raise RetryError(f"No human message found to retry: {e}", status=404) from e
    except RewindError as e:
        logger.exception(f"[RetryService] rewind failed: {e}")
        raise RetryError(f"Rewind failed: {e}", status=500) from e

    if rewind_result.status != "success":
        errors = "; ".join(rewind_result.errors)
        logger.error(f"[RetryService] rewind failed: {errors}")
        raise RetryError(f"Rewind failed: {errors}", status=500)

    # 3. 统一门面重派（路由 + intent_hint + session submit）
    async with route_lock_scope(thread_id, context):
        outcome = await dispatch_user_message(
            {
                "thread_id": thread_id,
                "message": content,
                "project_id": project_id,
                "references": references,
                "command_id": command_id,
                "model": model,
                "host_context": host_ctx,
            },
            source=source,
            input_channel=web_input,
            thread_id=thread_id,
            project_id=project_id,
            member_id=member_id,
            context=context,
            skip_l0=True,
            channel_kwargs={
                "is_retry": True,
                "skip_message_persistence": True,
            },
        )

        if outcome.msg is None:
            raise RetryError("invalid retry request", status=400)

        dispatch_result = outcome.inputs
        if dispatch_result is None or dispatch_result.status == DispatchStatus.FAILED:
            error = getattr(dispatch_result, "error", None) or "dispatch failed"
            raise RetryError(f"Retry dispatch failed: {error}", status=500)

        from app.core.engine.session.manager import session_manager

        await session_manager.submit(thread_id, dispatch_result.inputs)

    return RetryOutcome(
        ok=True,
        message_id=dispatch_result.message_id,
        target_message_id=target_message_id,
        content=content,
        files_reverted=rewind_result.reverted_file_count,
        removed_message_count=rewind_result.removed_message_count,
        rewind_errors=list(rewind_result.errors) if rewind_result.errors else [],
    )
