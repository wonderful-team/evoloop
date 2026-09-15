"""任务域事件订阅者。

- InboundMessageSubscriber：channel 归一化入站消息（InboundMessageEvent）
  → 任务入队（第三方消息源的唯一队列语义入口）；
- SessionReplyRouter：wakeup 会话终态 → 回复路由决策（发给谁），传输归 channel；
- DutyWakeupSubscriber：引擎 run 终态（`wakeup_` 线程）→ 唤醒 supervisor。

导入本模块即完成注册（@event_register 副作用）。
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.engine.event import AgentEventType
from app.core.events import system_bus
from app.core.events.decorators import event_register, event_subscribe
from app.core.events.registry import (
    InboundMessageEvent,
    OutboundReplyEvent,
    SystemEventType,
)
from app.domain.tasks.constants import QUOTA_COOLDOWN_MINUTES
from app.domain.tasks.runtime.wakeup import notify_duty_wakeup
from app.domain.tasks.service import EventSpecError, TaskQueueService

logger = logging.getLogger(__name__)


@event_register()
class InboundMessageSubscriber:
    """归一化入站消息 → 任务入队。

    本层只做队列语义（spec 校验/幂等/落任务），不解释业务；
    ``contact``（回复路由元数据）随 source_ref 落库，供完成侧路由消费。
    """

    @event_subscribe(SystemEventType.INBOUND_MESSAGE)
    async def on_inbound_message(self, event: InboundMessageEvent) -> None:
        spec: dict[str, Any] = {
            "title": event.title,
            "description": event.content,
            "project_id": event.project_id,
            "priority": event.priority,
        }
        if event.category:
            spec["category"] = event.category
        if event.risk_level:
            spec["risk_level"] = event.risk_level
        if event.contact:
            spec["contact"] = event.contact
        if event.channel:
            spec["channel"] = event.channel
        if event.start_in_hours is not None:
            spec["start_in_hours"] = event.start_in_hours

        try:
            task, created = await TaskQueueService.ingest_event(
                event.source_system, event.event_id, spec
            )
        except EventSpecError as e:
            logger.warning(
                "[InboundMessage] bad spec from %s: %s", event.source_system, e
            )
            return
        except Exception:  # noqa: BLE001
            logger.exception(
                "[InboundMessage] ingest failed (server=%s)", event.source_system
            )
            return

        logger.info(
            "[InboundMessage] %s task %s from %s (event=%s)",
            "created" if created else "deduped",
            task.id,
            event.source_system,
            event.event_id,
        )


@event_register()
class SessionReplyRouter:
    """wakeup 会话终态 → 回复路由决策（决策「发给谁」，传输归渠道）。

    队列任务线程（``wakeup_`` 前缀，last_thread_id 反查任务）成功完成后，
    按 task.source_ref 反查回复元数据：``contact`` + ``channel`` 齐备才发
    OutboundReplyEvent；纯工作项（无 contact）零动作。失败/取消的 run 不
    回复（走 reconciler 回队），语义与客服值守「成功才回」一致。
    """

    @event_subscribe(SystemEventType.SESSION_COMPLETED)
    async def on_session_completed(self, event: Any) -> None:
        data = getattr(event, "data", None)
        if data is None:
            return
        thread_id = str(getattr(data, "thread_id", "") or "")
        if not thread_id.startswith("wakeup_"):
            return
        summary = str(getattr(data, "summary", "") or "").strip()
        if not summary:
            return

        task = await TaskQueueService.get_task_by_thread(thread_id)
        if task is None:
            return
        source_ref = task.source_ref or {}
        contact = str(source_ref.get("contact") or "").strip()
        channel = str(source_ref.get("channel") or "").strip()
        if not contact or not channel:
            return  # 纯工作项：无回复语义

        await system_bus.publish(OutboundReplyEvent(
            source="domain.tasks",
            channel=channel,
            recipient=contact,
            content=summary,
            project_id=task.project_id or 0,
            source_system=str(source_ref.get("source_system") or ""),
            thread_id=thread_id,
        ))
        logger.info(
            "[SessionReplyRouter] reply routed (task=%s, channel=%s, contact=%s)",
            task.id,
            channel,
            contact,
        )


@event_register()
class DutyWakeupSubscriber:
    """AgentRunCompletedEvent（`wakeup_` 线程）→ 唤醒 supervisor 任务切换。

    终态事件由 activity_monitor 全终态发布（含 HUMAN_INTERRUPT 挂起），
    本订阅者是"事件做加速"的接入点；丢失时 60s 兜底收敛。
    """

    @event_subscribe(AgentEventType.RUN_COMPLETED)
    async def on_agent_run_completed(self, event: Any) -> None:

        thread_id = str(getattr(event, "thread_id", "") or "")
        if not thread_id.startswith("wakeup_"):
            return
        logger.info("[DutyWakeup] run completed: %s → wakeup", thread_id)
        # 配额熔断（事件路径，先于 reconciler 的稳态兜底）：
        # 429 场景下若只切换任务，串行 drain 会把队列挨个打一遍 429。
        status = getattr(event, "status", None)
        status_value = getattr(status, "value", None) or str(status or "")
        if status_value == "quota_exhausted":
            from app.domain.tasks.runtime.dispatcher import pause_duty_until

            pause_duty_until(
                _quota_reset_time(event)
                or datetime.now(timezone.utc) + timedelta(minutes=QUOTA_COOLDOWN_MINUTES)
            )
        notify_duty_wakeup()


def _quota_reset_time(event: Any) -> datetime | None:
    """从 429 错误文本里提取配额重置时间（如 "reset at 2026-09-14 00:00:00 +0800"）。

    解析不到（payload 无 summary / 格式变化）返回 None，调用方落到缺省冷却。
    """
    payload = getattr(event, "payload", None) or {}
    # end_run 路径（quota 终态事件）错误文本在 outcome；runner 异常路径在 summary
    summary = str(payload.get("outcome") or payload.get("summary") or "")
    m = re.search(
        r"reset at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([+-]\d{2}:?\d{2})", summary
    )
    if not m:
        return None
    try:
        naive = datetime.fromisoformat(m.group(1))
        sign = -1 if m.group(2).startswith("-") else 1
        digits = m.group(2).lstrip("+-").replace(":", "")
        offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:])) * sign
        return naive.replace(tzinfo=timezone(offset)) + timedelta(minutes=1)
    except (ValueError, TypeError):
        return None


inbound_message_subscriber = InboundMessageSubscriber()
session_reply_router = SessionReplyRouter()
duty_wakeup_subscriber = DutyWakeupSubscriber()


@event_register()
class SupervisorLifecycleSubscriber:
    """supervisor 主循环生命周期：APP_STARTED 拉起 / APP_STOPPING 停止。

    连续运行时的宿主自包含于本域（模块自治），composition root 只发布
    生命周期事件。worker 进程（bin/run_worker.py）不发布 APP_STARTED，
    单 drainer 红线由进程归属保证。
    """

    def __init__(self) -> None:
        self.supervisor_task: asyncio.Task | None = None

    @event_subscribe(SystemEventType.APP_STARTED)
    async def on_app_started(self, event: Any) -> None:
        from app.domain.tasks.runtime.supervisor import run_supervisor_forever

        if self.supervisor_task is not None and not self.supervisor_task.done():
            logger.warning("[DutySupervisor] 已在运行，忽略重复启动")
            return
        self.supervisor_task = asyncio.create_task(
            run_supervisor_forever(),
            name="duty-supervisor",
        )
        # 死亡可见性：主循环异常退出（非取消）必须被人看见——值守全停是
        # CRITICAL 级事件。不做自动重启：crash loop 会掩盖系统性 bug 并烧配额，
        # 主循环死亡必须被排查而不是被掩盖。
        self.supervisor_task.add_done_callback(self._on_supervisor_done)
        logger.info("[DutySupervisor] 已随 APP_STARTED 启动 (API 进程)")

    @staticmethod
    def _on_supervisor_done(task: asyncio.Task) -> None:
        if task.cancelled():
            return  # 正常停止路径
        exc = task.exception()
        logger.critical(
            "[DutySupervisor] 主循环异常退出，值守已停摆（队列不再排空）: %r",
            exc,
            exc_info=exc,
        )

    @event_subscribe(SystemEventType.APP_STOPPING)
    async def on_app_stopping(self, event: Any) -> None:
        if self.supervisor_task is None:
            return
        self.supervisor_task.cancel()
        try:
            await self.supervisor_task
        except asyncio.CancelledError:
            pass
        logger.info("[DutySupervisor] 已随 APP_STOPPING 停止")
        self.supervisor_task = None


supervisor_lifecycle_subscriber = SupervisorLifecycleSubscriber()
