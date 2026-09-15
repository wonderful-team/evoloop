"""Duty dispatcher — 任务队列的派发编排（domain 层）。

单 drainer：任务队列派发只经由本模块（supervisor 循环调用），tick 不再派发。
串行消费，事件/超时驱动接续。线程策略：
- 纯工作项：每任务唯一线程 `wakeup_{pid}_{taskid}`（1:1 plan）；
- 会话类（source_ref.contact）：固定线程 `wakeup_{pid}_{contact}`，同一联系人的
  对话历史跨任务累积（客服多轮语义），串行 drain 保证不并发。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.domain.tasks.constants import (
    WAKEUP_RUN_DEADLINE_SECONDS,
)
from app.domain.tasks.schemas import WakeupTask
from app.domain.tasks.service import TaskQueueService

logger = logging.getLogger(__name__)

# ── 配额熔断（账号级）────────────────────────────────────
# quota_exhausted 的 run 终态后，暂停值守派发一段时间：否则串行 drain 会把
# 队列里所有任务挨个打一遍 429（实测：每 ~6s 烧一次），配额重置前纯烧日志。
# 账号级配额 → 全局熔断（进程内时间戳）；reconciler 在终态判定时触发。
_quota_paused_until: datetime | None = None


def pause_duty_for(minutes: float) -> None:
    """quota 熔断：暂停值守派发 N 分钟（幂等，取最晚者）。"""
    pause_duty_until(datetime.now(timezone.utc) + timedelta(minutes=minutes))


def pause_duty_until(until: datetime) -> None:
    """quota 熔断：暂停值守派发到指定时刻（幂等，取最晚者）。"""
    global _quota_paused_until
    if _quota_paused_until is None or until > _quota_paused_until:
        _quota_paused_until = until
        logger.warning(
            "[DutyDispatcher] 配额熔断：暂停值守派发（至 %s）",
            until.isoformat(),
        )


def duty_paused(now: datetime | None = None) -> bool:
    """是否处于配额熔断窗口。"""
    until = _quota_paused_until
    if until is None:
        return False
    if (now or datetime.now(timezone.utc)) >= until:
        return False
    return True


async def _run_wakeup_with_deadline(thread_id: str, inputs: dict) -> None:
    """后台跑一个 wakeup run，超时硬取消（CancelledError → CANCELLED 终态）。"""
    from app.core.engine.agent import run_agent_background

    run_task = asyncio.create_task(run_agent_background(thread_id, inputs))
    try:
        await asyncio.wait_for(run_task, timeout=WAKEUP_RUN_DEADLINE_SECONDS)
    except asyncio.TimeoutError:
        logger.error(
            "[DutyDispatcher] wakeup run %s 超过 %ss 硬截止，强制取消（任务由 reconciler 回队）",
            thread_id,
            WAKEUP_RUN_DEADLINE_SECONDS,
        )


async def dispatch_due_tasks() -> None:
    """Drain due project_tasks: one run per task, priority → due order.

    Called ONLY by the duty supervisor (infrastructure/scheduler/supervisor.py)
    — the single drainer. Serial by design: each task gets its own thread/run
    with a 1:1 plan (plan is thread-scoped). Tasks are claimed atomically by
    the status machine; the drain stops when nothing new is claimable, or when
    a dispatch fails (avoid tight-loop redispatch).
    """
    from app.core.engine.capability_profiles import list_domains
    from app.core.engine.dispatch import DispatchStatus, dispatch_agent_run
    from app.core.project.utils import get_project_path
    from app.utils.id import unique_id
    from app.utils.template import render_template

    if duty_paused():
        logger.info("[DutyDispatcher] 配额熔断中，本轮暂停值守派发")
        return

    # 全局总闸（托盘"停止值守"）：关 = 整个值守引擎不排空。必须在任何
    # 认领/派发之前检查——用户心智里这个开关就是"什么都不跑"，而项目分闸
    # 可能因实验遗留为 true（历史事故：总闸关了任务照跑，托盘停不下来）。
    from app.core.channel.duty.config import load_global_duty_config

    if not load_global_duty_config().get("enabled"):
        return
    attempted: set[str] = set()
    while True:
        due = await TaskQueueService.claim_due_tasks()
        t = next((x for x in due if x.id not in attempted), None)
        if t is None:
            return
        attempted.add(t.id)

        project_id = t.project_id or 0
        category = str((t.task_data or {}).get("category") or "default")
        # 线程名强制 `wakeup_` 前缀：reconciler 豁免/判死、事件订阅过滤、
        # stop 切线程都依赖该前缀。
        # 会话连续性（contact 任务）：同一联系人固定线程 `wakeup_{pid}_{contact}`
        # （无 epoch 后缀），对话历史在引擎线程里跨任务累积——客服多轮语义的前提。
        # 串行 drain 保证同线程不并发；任务经 last_thread_id 反查（get_task_by_thread）。
        # 纯工作项（无 contact）：`wakeup_{pid}_{taskid}` 唯一线程（1:1 plan）。
        contact = str((t.source_ref or {}).get("contact") or "").strip()
        if contact:
            thread_id = f"wakeup_{project_id}_{contact}"
        else:
            thread_id = unique_id(f"wakeup_{project_id}_{t.id}")

        # duty runs have no host page: resolve the domain from the
        # project-declared capability profile (profile-first assembly)
        project_dir = await get_project_path(project_id)
        domains = list_domains(project_dir) if project_dir else []
        domain = domains[0] if len(domains) == 1 else None

        prompt = render_template(
            "core/engine/tasks/task_wakeup.prompt.j2",
            category=category,
            task=WakeupTask(
                id=t.id,
                status=t.status,
                title=(t.task_data or {}).get("title", ""),
                instruction=t.description or "",
                priority=(t.task_data or {}).get("priority", "medium"),
                risk=t.risk_level or "T3",
                due=(t.due_at or t.next_run_at).isoformat()
                if (t.due_at or t.next_run_at)
                else "now",
                feedback=(t.acceptance or {}).get("feedback") or "",
            ),
        )
        result = await dispatch_agent_run(
            thread_id=thread_id,
            message_content=prompt,
            project_id=project_id or None,
            member_id=await TaskQueueService.resolve_member_id(t),
            metadata={
                "source": "duty",
                "source_task_id": t.id,
                "channel_name": str((t.source_ref or {}).get("channel") or ""),
                "goal_prefix": "[Wakeup] ",
                **(
                    {
                        "intent_hint": {
                            "domain": domain,
                            "intent": "domain_classified",
                            "reason": "duty wakeup (project profile)",
                        }
                    }
                    if domain
                    else {}
                ),
            },
        )
        if result.status == DispatchStatus.FAILED:
            logger.error(
                f"[DutyDispatcher] wakeup dispatch failed for task {t.id}: {result.error}"
            )
            return  # avoid tight-loop redispatching a broken dispatch
        if result.inputs:
            logger.info(
                f"[DutyDispatcher] wakeup run started (task={t.id}, thread={thread_id})"
            )
            await _run_wakeup_with_deadline(thread_id, result.inputs)
            # loop continues: run finished (or HITL-suspended) -> claim next
