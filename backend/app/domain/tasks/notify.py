"""值守 HITL/告警手机推送（单出口，2026-09-25 收敛）。

历史上三处（advance signoff 推送 / dispatcher 断链告警 / reconciler
signoff 24h 提醒）各自重复「#T-n 标签拼装 + MobileChannel.send_hitl_request
+ try/except」样板——收拢为一个入口，prompt 与 request_id 由调用方给出，
通道开关（MOBILE_SYNC_ENABLED）与失败降级（logger.exception 不阻断业务）
在此统一。
"""

from __future__ import annotations

import logging

from app.models.project import ProjectTask

logger = logging.getLogger(__name__)


def task_label(task: ProjectTask) -> str:
    """任务短标签：#T-<n>（缺编号回退 id 前 8 位）。"""
    from app.domain.tasks.service import task_number

    no = task_number(task)
    return f"#T-{no}" if no else task.id[:8]


async def push_hitl_notice(
    task: ProjectTask,
    *,
    request_id: str,
    kind: str,
    prompt: str,
) -> None:
    """向手机通道推一条值守人工触达（开关关闭/失败都不阻断业务链路）。"""
    try:
        from app.core.channel.base import ChannelContext
        from app.core.channel.output.mobile_channel import MobileChannel
        from app.core.config import settings as _settings

        if _settings.MOBILE_SYNC_ENABLED:
            await MobileChannel().send_hitl_request(
                request_id=request_id,
                request_type="confirmation",
                prompt=prompt,
                ctx=ChannelContext(
                    thread_id=task.origin_thread_id or task.id,
                    project_id=task.project_id,
                ),
                metadata={"kind": kind, "task_id": task.id},
            )
    except Exception:
        logger.exception("[TaskNotice] push failed (task=%s, kind=%s)", task.id, kind)
