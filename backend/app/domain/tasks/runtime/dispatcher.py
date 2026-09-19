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
from app.domain.tasks.events import publish_workflow_event
from app.domain.tasks.runtime.agent import AgentRuntimeError, EvoloopAgentRuntimeAdapter
from app.domain.tasks.schemas import WakeupTask
from app.domain.tasks.service import TaskQueueService
from app.domain.tasks.workflows import WorkflowError, WorkflowService

logger = logging.getLogger(__name__)


async def resolve_wakeup_domain(project_id: int, instruction: str) -> tuple[str | None, str]:
    """值守唤醒的域解析（供派发 hint）。

    1. profile-first：项目工作目录恰好声明唯一域 → 直接采用（≈host 权威）；
    2. L1 域标注兜底：与文本消息 ``skip_l0`` 路径同源组件
       （``domain_classifier.predict``）、同置信度门槛——值守此前漏接了
       L1（文本客服值守都走），跨项目任务（工作目录未声明域）据此首轮
       即可按域装配。
    3. 分不出/低置信 → ``None``：fail-open（全量面 + 包反哺兜底），无回归。
    """
    from app.core.engine.capability_profiles import list_domains
    from app.core.project.utils import get_project_path

    project_dir = await get_project_path(project_id)
    domains = list_domains(project_dir) if project_dir else []
    if len(domains) == 1:
        return domains[0], "duty wakeup (project profile)"

    if not instruction.strip():
        return None, ""

    from app.core.routing import constants as routing_constants
    from app.core.routing import domain_classifier

    label, conf = await asyncio.to_thread(domain_classifier.predict, instruction)
    if label and conf >= routing_constants.CONFIDENCE_THRESHOLD:
        logger.info(
            "[DutyDispatcher] L1 domain label: '%s' (conf=%.2f, task project=%s)",
            label,
            conf,
            project_id,
        )
        return label, "duty wakeup (L1)"
    logger.info(
        "[DutyDispatcher] L1 domain unresolved (label=%s conf=%.2f); full surface",
        label,
        conf,
    )
    return None, ""

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


async def auto_retry_failed_tasks() -> None:
    """Give transiently-failed tasks ONE automatic requeue (10 min backoff).

    Non-retryable causes (content inspection / missing model config) never
    auto-retry — they stay failed and surface in the operator queue.
    """
    from app.domain.tasks.constants import (
        FAILED_AUTO_RETRY_BUDGET,
        FAILED_AUTO_RETRY_DELAY_SECONDS,
        NON_RETRYABLE_ERROR_MARKERS,
    )

    rows = await TaskQueueService.list_tasks(status="failed", limit=50)
    for t in rows:
        td = t.task_data or {}
        tries = int(td.get("workflow_auto_retry") or 0)
        if tries >= FAILED_AUTO_RETRY_BUDGET:
            continue
        last_error = str(td.get("last_error") or "")
        if any(marker in last_error for marker in NON_RETRYABLE_ERROR_MARKERS):
            continue
        td["workflow_auto_retry"] = tries + 1
        td["last_result"] = f"auto retry {tries + 1}: {last_error[:80]}"
        from datetime import timedelta, timezone

        from app.infrastructure.database.sql.database import session_scope

        async with session_scope() as session:
            from sqlalchemy import update as sa_update

            from app.models.project import ProjectTask

            await session.execute(
                sa_update(ProjectTask)
                .where(ProjectTask.id == t.id)
                .values(
                    status="pending",
                    task_data=td,
                    due_at=datetime.now(timezone.utc)
                    + timedelta(seconds=FAILED_AUTO_RETRY_DELAY_SECONDS),
                )
            )
        logger.info(
            "[DutyDispatcher] auto-retry failed task %s (attempt %s)",
            t.id,
            tries + 1,
        )


async def dispatch_due_tasks() -> None:
    """Drain due project_tasks: one run per task, priority → due order.

    Called ONLY by the duty supervisor (infrastructure/scheduler/supervisor.py)
    — the single drainer. Serial by design: each task gets its own thread/run
    with a 1:1 plan (plan is thread-scoped). Tasks are claimed atomically by
    the status machine; the drain stops when nothing new is claimable, or when
    a dispatch fails (avoid tight-loop redispatch).
    """
    from app.core.engine.dispatch import DispatchStatus, dispatch_agent_run
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

        if (t.task_data or {}).get("workflow_runtime") == "evoloop":
            try:
                await EvoloopAgentRuntimeAdapter.run(t)
            except (AgentRuntimeError, WorkflowError) as exc:
                logger.exception(
                    "[DutyDispatcher] Evoloop Agent workflow task failed: %s", t.id
                )
                from app.domain.tasks.constants import NON_RETRYABLE_ERROR_MARKERS

                reason = str(exc)
                if any(marker in reason for marker in NON_RETRYABLE_ERROR_MARKERS):
                    # 确定性失败（内容审查/配置缺失）：重试不会好，直接终态
                    logger.warning(
                        "[DutyDispatcher] non-retryable error, failing task %s directly",
                        t.id,
                    )
                    await TaskQueueService.advance_task(t.id, "failed", result=reason)
                    workflow_id = str((t.task_data or {}).get("workflow_id") or "")
                    if workflow_id:
                        await WorkflowService.refresh_status(workflow_id)
                        await publish_workflow_event(
                            workflow_id,
                            event="task_retry_scheduled",
                            task_id=t.id,
                            stage=str((t.task_data or {}).get("workflow_stage") or ""),
                            status="failed",
                        )
                    continue
                requeued_task = await TaskQueueService.requeue_workflow_task(
                    t.id,
                    str(exc),
                )
                fresh_task = requeued_task or await TaskQueueService.get_task(t.id)
                if fresh_task is not None and fresh_task.status == "in_progress":
                    await TaskQueueService.advance_task(
                        t.id,
                        "failed",
                        result=str(exc),
                    )
                workflow_id = str((t.task_data or {}).get("workflow_id") or "")
                if workflow_id:
                    await WorkflowService.refresh_status(workflow_id)
                    await publish_workflow_event(
                        workflow_id,
                        event="task_retry_scheduled",
                        task_id=t.id,
                        stage=str((t.task_data or {}).get("workflow_stage") or ""),
                        status=(fresh_task.status if fresh_task else "failed"),
                    )
            continue

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

        # duty runs have no host page: 域解析 profile-first → L1 域标注兜底
        # （与文本消息路径同源；此前值守漏接 L1，跨项目任务首轮全量）
        domain, hint_reason = await resolve_wakeup_domain(
            project_id, t.description or ""
        )

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
                            "reason": hint_reason,
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
