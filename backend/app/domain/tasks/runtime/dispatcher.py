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
    DISPATCH_CLAIM_CIRCUIT_LIMIT,
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
        # 评审收敛（2 轮转人工仲裁）的 failed 是终态，绝不 auto-retry——
        # 否则评审-返工循环重开，执行者会被无限加码
        if (t.acceptance or {}).get("escalated"):
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




async def _notify_dep_failure(task, failed_up: list) -> None:
    """上游失败（含 escalated 仲裁）→ 手机推送一次断链告警（防重标记）。

    不自动级联取消下游——上游可能被用户 rerun 修复；通知让人来裁决。
    """
    td = dict(task.task_data or {})
    if td.get("dep_failure_notified"):
        return
    td["dep_failure_notified"] = True
    from app.infrastructure.database.sql.database import session_scope
    from sqlalchemy import update

    from app.models.project import ProjectTask

    async with session_scope() as session:
        await session.execute(
            update(ProjectTask).where(ProjectTask.id == task.id).values(task_data=td)
        )
    try:
        from app.core.channel.base import ChannelContext
        from app.core.channel.output.mobile_channel import MobileChannel
        from app.core.config import settings as _settings

        if _settings.MOBILE_SYNC_ENABLED:
            no = td.get("task_no")
            label = f"#T-{no}" if no else task.id[:8]
            names = ", ".join(
                f"#{(u.task_data or {}).get('task_no') or u.id[:8]}"
                for u in failed_up
            )
            await MobileChannel().send_hitl_request(
                request_id=f"dep-blocked-{task.id}",
                request_type="confirmation",
                prompt=f"任务链断在「{names}」（失败），{len(failed_up) and ''}下游任务 {label}「{td.get('title', '')[:36]}」已阻塞待裁决：修复重跑上游 / 调整链路。",
                ctx=ChannelContext(thread_id=task.origin_thread_id or task.id, project_id=task.project_id),
                metadata={"kind": "dep_blocked", "task_id": task.id},
            )
    except Exception:
        logger.exception("[DutyDispatcher] dep-blocked push failed")


async def _deps_satisfied(task) -> bool:
    """依赖链 gating：task_data.dependencies 里的上游任务未全部 completed
    则暂不派发（pending 依赖的声明性记录在此变为执行顺序约束）。依赖任务
    缺失/删除视为不满足（数据被清理时不放行，避免孤儿任务乱跑）。

    上游存在 failed 时触发断链告警（手机推送一次），下游保持 blocked 等
    人工裁决（rerun 修复上游 / 调整链路）。
    """
    dep_ids = (task.task_data or {}).get("dependencies") or []
    if not dep_ids:
        return True
    from sqlalchemy import select

    from app.infrastructure.database.sql.database import session_scope
    from app.models.project import ProjectTask

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(ProjectTask.id, ProjectTask.status).where(
                    ProjectTask.id.in_([str(d) for d in dep_ids])
                )
            )
        ).all()
    status_by_id = {rid: st for rid, st in rows}
    failed_up = [t for t in rows if t[1] == "failed"]
    if failed_up and not (task.task_data or {}).get("dep_failure_notified"):
        objs = []
        async with session_scope() as session:
            objs = (
                (
                    await session.execute(
                        select(ProjectTask).where(
                            ProjectTask.id.in_([f[0] for f in failed_up])
                        )
                    )
                )
                .scalars()
                .all()
            )
        await _notify_dep_failure(task, list(objs))
    return all(
        status_by_id.get(str(d)) == "completed"
        for d in (str(x) for x in dep_ids)
    )




async def _build_upstream_context(task) -> str:
    """依赖任务的产出摘要注入唤醒 payload。

    upstream deps 的 last_result（结论摘要）+ task_artifacts 清单（产物
    文件路径，执行者可用 read 抽查全文）。失败静默（通知失败不影响派发）。
    """
    dep_ids = (task.task_data or {}).get("dependencies") or []
    if not dep_ids:
        return ""
    dep_ids = [str(d) for d in dep_ids]
    from sqlalchemy import select

    from app.infrastructure.database.sql.database import session_scope
    from app.models.project import ProjectTask
    from app.models.task_workflow import TaskArtifact

    try:
        async with session_scope() as session:
            result = await session.execute(
                select(ProjectTask).where(ProjectTask.id.in_(dep_ids))
            )
            rows = result.scalars().all()
            ares = await session.execute(
                select(TaskArtifact).where(TaskArtifact.task_id.in_(dep_ids))
            )
            arts = ares.scalars().all()
        arts_by_task: dict[str, list] = {}
        for a in arts:
            arts_by_task.setdefault(str(a.task_id), []).append(a)
        lines = ["## 上游任务产出（本任务执行时应直接引用，勿重复调研）"]
        for up in sorted(rows, key=lambda x: (x.task_no or 0)):
            no = (up.task_data or {}).get("task_no")
            label = f"#T-{no}" if no else up.id[:8]
            result = (up.task_data or {}).get("last_result") or ""
            lines.append(
                f"- {label}「{(up.task_data or {}).get('title', '')[:40]}」结论：{result[:300]}"
            )
            for a in arts_by_task.get(up.id, [])[:3]:
                lines.append(f"  · 产物：{getattr(a, 'file_path', '') or getattr(a, 'name', '')}")
        return "\n".join(lines)
    except Exception:
        logger.exception("[DutyDispatcher] upstream context build failed")
        return ""


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
        deps_blocked = 0
        t = None
        for cand in due:
            if cand.id in attempted:
                continue
            if not await _deps_satisfied(cand):
                deps_blocked += 1
                continue
            t = cand
            break
        if t is None:
            if deps_blocked:
                logger.info(
                    "[DutyDispatcher] %d due task(s) waiting on upstream dependencies",
                    deps_blocked,
                )
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

        # ── 派发即认领（claim-then-persist，AGENTS.md 断裂修复记录 #6）──
        # 派发前系统侧原子认领（pending→in_progress+绑线程+dispatch_count++），
        # 与 recurring「认领即推进 next_run_at」对齐：run 结束时任务必已被
        # 系统持有，DutyWakeupSubscriber 再唤醒也只会认领到**其他** pending
        # 任务，从构造上关断「run 完成 × 任务未推进」的紧派发环。
        claimed = await TaskQueueService.claim_for_dispatch(t.id, thread_id)
        if claimed is None:
            continue  # 认领失败（并发/状态已变）→ 本轮不派发
        # 熔断（认领后判定，走合法转移 in_progress→failed）：认领次数达阈值
        # 仍无终态 = agent 未履约 take/update_status 或派发反复失败 → 强制
        # 终态，把毒任务显式炸出来而不是无限烧 LLM。
        if int((claimed.task_data or {}).get("dispatch_count") or 0) >= (
            DISPATCH_CLAIM_CIRCUIT_LIMIT
        ):
            await TaskQueueService.advance_task(
                t.id,
                "failed",
                result=(
                    f"值守派发熔断：{DISPATCH_CLAIM_CIRCUIT_LIMIT} 次派发未推进"
                    "任务终态（未 take/未 update_status）"
                ),
                by="system",
            )
            continue

        # duty runs have no host page: 域解析 profile-first → L1 域标注兜底
        # （与文本消息路径同源；此前值守漏接 L1，跨项目任务首轮全量）
        domain, hint_reason = await resolve_wakeup_domain(
            project_id, t.description or ""
        )

        # 跨任务产出传递：依赖任务的结论摘要与产物链接注入唤醒 payload——
        # 链式任务的执行者（独立 wakeup 线程）拿不到上游 thread 的消息，
        # 缺了这段它只能重新调研或编造（链式任务的命脉）。
        instruction_text = t.description or ""
        upstream_note = await _build_upstream_context(t)
        if upstream_note:
            instruction_text = f"{instruction_text}\n\n{upstream_note}"

        prompt = render_template(
            "core/engine/tasks/task_wakeup.prompt.j2",
            category=category,
            task=WakeupTask(
                id=t.id,
                status=t.status,
                title=(t.task_data or {}).get("title", ""),
                instruction=instruction_text,
                priority=(t.task_data or {}).get("priority", "medium"),
                risk=t.risk_level or "T3",
                due=(t.due_at or t.next_run_at).isoformat()
                if (t.due_at or t.next_run_at)
                else "now",
                feedback=(t.acceptance or {}).get("feedback") or "",
            ),
        )
        try:
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
        except Exception:
            # 派发异常：回滚认领占位再上抛（supervisor 记录 drain failed），
            # 任务回队由下一拍重试；dispatch_count 已累计，反复失败会走熔断。
            await TaskQueueService.release_dispatch_claim(t.id, thread_id)
            raise
        if result.status == DispatchStatus.FAILED:
            logger.error(
                f"[DutyDispatcher] wakeup dispatch failed for task {t.id}: {result.error}"
            )
            # 派发失败：回滚认领（pending），60s 兜底重试；连续失败由熔断收敛。
            await TaskQueueService.release_dispatch_claim(t.id, thread_id)
            return  # avoid tight-loop redispatching a broken dispatch
        if result.inputs:
            logger.info(
                f"[DutyDispatcher] wakeup run started (task={t.id}, thread={thread_id})"
            )
            await _run_wakeup_with_deadline(thread_id, result.inputs)
            # loop continues: run finished (or HITL-suspended) -> claim next
