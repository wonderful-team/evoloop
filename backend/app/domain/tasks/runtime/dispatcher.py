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
import time
from datetime import datetime, timedelta, timezone

from app.domain.tasks.constants import (
    DISPATCH_CLAIM_CIRCUIT_LIMIT,
    WAKEUP_RUN_DEADLINE_SECONDS,
)
from app.domain.tasks.events import publish_queue_drained
from app.domain.tasks.service import (
    TaskQueueService,
    task_category,
    task_dependencies,
    task_dispatch_count,
    task_last_error,
    task_last_result,
    task_number,
    task_priority,
    task_skills,
    task_title,
    task_version,
)

logger = logging.getLogger(__name__)

# 全局并发护栏：值守 drain 一次只跑一个 wakeup run。
# 当前 supervisor 单循环已天然串行，此 semaphore 把契约显式化，防止未来改
# 动把 run 改成 fire-and-forget 后破坏“任务一个一个执行”的用户心智。
MAX_CONCURRENT_WAKEUP_RUNS = 1
_wakeup_run_semaphore = asyncio.Semaphore(MAX_CONCURRENT_WAKEUP_RUNS)


async def resolve_wakeup_domain(
    project_id: int, instruction: str
) -> tuple[str | None, str]:
    """值守唤醒的域解析（供派发 hint）。

    0. 工作空间任务（pid=0）不绑定任何项目域 → 直接 fail-open：L1 按
       措辞猜域会把工作空间任务误装进某个项目的受限 profile（2026-09-23
       实测事故：Upwork 侦察轮描述被 L1 高置信分类为 ecommerce，继承了
       商城 profile 的 native_tools 白名单，bash/文件工具全被裁掉，
       opencli/落盘全断 → HITL 挂起）。
    1. profile-first：项目工作目录恰好声明唯一域 → 直接采用（≈host 权威）；
    2. L1 域标注兜底：与文本消息 ``skip_l0`` 路径同源组件
       （``domain_classifier.predict``）、同置信度门槛——值守此前漏接了
       L1（文本客服值守都走），跨项目任务（工作目录未声明域）据此首轮
       即可按域装配。
    3. 分不出/低置信 → ``None``：fail-open（全量面 + 包反哺兜底），无回归。
    """
    if project_id == 0:
        return None, ""

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
    from app.core.engine.agent_run_registry import agent_run_registry
    from app.core.engine.session.manager import session_manager
    from app.core.engine.session.session import AgentSession

    session = AgentSession(thread_id)
    session_manager._sessions[thread_id] = session

    run_task = asyncio.create_task(run_agent_background(thread_id, inputs))
    await agent_run_registry.register_run(
        thread_id, run_task, description=f"wakeup:{thread_id}"
    )
    t0 = time.monotonic()
    try:
        await asyncio.wait_for(run_task, timeout=WAKEUP_RUN_DEADLINE_SECONDS)
        logger.info(
            "[DutyDispatcher] run_task completed in %.3fs (thread=%s)",
            time.monotonic() - t0,
            thread_id,
        )
    except asyncio.TimeoutError:
        logger.error(
            "[DutyDispatcher] wakeup run %s 超过 %ss 硬截止，强制取消（任务由 reconciler 回队）",
            thread_id,
            WAKEUP_RUN_DEADLINE_SECONDS,
        )
        run_task.cancel()
        try:
            await run_task
        except (asyncio.CancelledError, Exception):
            pass
    except asyncio.CancelledError:
        logger.info(
            "[DutyDispatcher] wakeup run %s was cancelled by request", thread_id
        )
        if not run_task.done():
            run_task.cancel()
            try:
                await run_task
            except (asyncio.CancelledError, Exception):
                pass
    finally:
        session_manager._sessions.pop(thread_id, None)
        async with agent_run_registry._lock:
            agent_run_registry._records.pop(thread_id, None)
        try:
            from app.core.execution.terminal.background import task_manager

            await task_manager.cancel_thread_tasks(thread_id)
        except Exception:
            pass


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
        last_error = task_last_error(t) or ""
        last_result = t.last_result or ""
        err_text = f"{last_error} {last_result}"
        if any(marker in err_text for marker in NON_RETRYABLE_ERROR_MARKERS):
            continue
        td["workflow_auto_retry"] = tries + 1
        from datetime import timedelta, timezone

        from app.infrastructure.database.sql.database import session_scope

        async with session_scope() as session:
            from sqlalchemy import update as sa_update

            from app.models.project import ProjectTask

            result_update = await session.execute(
                sa_update(ProjectTask)
                .where(
                    ProjectTask.id == t.id,
                    ProjectTask.version == task_version(t),
                )
                .values(
                    status="pending",
                    task_data=td,
                    last_result=f"auto retry {tries + 1}: {last_error[:80]}",
                    version=task_version(t) + 1,
                    due_at=datetime.now(timezone.utc)
                    + timedelta(seconds=FAILED_AUTO_RETRY_DELAY_SECONDS),
                )
            )
            if result_update.rowcount == 0:
                continue
        logger.info(
            "[DutyDispatcher] auto-retry failed task %s (attempt %s)",
            t.id,
            tries + 1,
        )


_prev_attempted = 0


async def _maybe_publish_queue_drained(attempted: int) -> None:
    """值守排空沿检测：上一轮有派发、本轮无派发 → 本轮值守结束。

    串行 drain 下每轮结束时 in_progress 必为 0，故不能拿 in_progress==0
    当条件（每拍都成立）；以"派发活动沿"为准：prev>0 且 now==0 才是真正
    的收尾沿，空闲轮（prev==0）不重复广播。发布前再查一次 in_progress
    兜底（派发失败回滚/依赖阻塞轮的误报）。

    前端收到 queue_drained 后在状态条展示"本轮值守完成"一次性汇总。
    """
    global _prev_attempted
    try:
        if attempted > 0:
            _prev_attempted = attempted
            return

        from sqlalchemy import func, select

        from app.infrastructure.database.sql.database import session_scope
        from app.models.project import ProjectTask

        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(ProjectTask.status, func.count()).group_by(
                        ProjectTask.status
                    )
                )
            ).all()
        counts = {r[0]: int(r[1]) for r in rows}
        # 仍有活动 run（并发收尾/依赖阻塞轮）：保持沿状态不清零，下一拍
        # in_progress 归零时照常触发——若在此清零，并发收尾的第一个完成沿
        # 被吞掉后沿状态丢失，最后一个任务结束时战报永远不发（实测）。
        if counts.get("in_progress", 0) > 0:
            return
        if _prev_attempted > 0:
            _prev_attempted = 0
        else:
            return
        await publish_queue_drained(
            completed=counts.get("completed", 0),
            failed=counts.get("failed", 0),
            waiting=counts.get("waiting_acceptance", 0),
            pending=counts.get("pending", 0),
        )
        logger.info(
            "[DutyDispatcher] queue drained: completed=%s failed=%s waiting=%s pending=%s",
            counts.get("completed", 0),
            counts.get("failed", 0),
            counts.get("waiting_acceptance", 0),
            counts.get("pending", 0),
        )
    except Exception:
        logger.exception("[DutyDispatcher] queue_drained publish failed")


async def _notify_dep_failure(task, failed_up: list) -> None:
    """上游失败（含 escalated 仲裁）→ 手机推送一次断链告警（防重标记）。

    不自动级联取消下游——上游可能被用户 rerun 修复；通知让人来裁决。
    """
    td = dict(task.task_data or {})
    if td.get("dep_failure_notified"):
        return
    td["dep_failure_notified"] = True
    from sqlalchemy import update

    from app.infrastructure.database.sql.database import session_scope
    from app.models.project import ProjectTask

    async with session_scope() as session:
        await session.execute(
            update(ProjectTask).where(ProjectTask.id == task.id).values(task_data=td)
        )
    from app.domain.tasks.notify import push_hitl_notice, task_label

    names = ", ".join(task_label(u) for u in failed_up)
    label = task_label(task)
    await push_hitl_notice(
        task,
        request_id=f"dep-blocked-{task.id}",
        kind="dep_blocked",
        prompt=f"任务链断在「{names}」（失败），{len(failed_up) and ''}下游任务 {label}「{td.get('title', '')[:36]}」已阻塞待裁决：修复重跑上游 / 调整链路。",
    )


async def _deps_satisfied(task) -> bool:
    """依赖链 gating（单一实现）：规则本体在
    ``TaskQueueService.evaluate_dependency_gate``（claim 扫描与派发闸共用，
    含 recurring lineage-only 豁免与"依赖缺失不放行"）。本函数只承担
    派发侧副作用——上游 failed 时触发一次断链告警（手机推送一次，防重
    标记），下游保持 blocked 等人工裁决（rerun 修复上游 / 调整链路）。
    """
    dep_ids = task_dependencies(task)
    if not dep_ids:
        return True
    satisfied, failed_up = await TaskQueueService.evaluate_dependency_gate(task)
    if failed_up and not (task.task_data or {}).get("dep_failure_notified"):
        await _notify_dep_failure(task, failed_up)
    return satisfied


async def _build_upstream_context(task) -> str:
    """依赖任务的产出摘要注入唤醒 payload。

    upstream deps 的 last_result（结论摘要）+ task_artifacts 清单（产物
    文件路径，执行者可用 read 抽查全文）。失败静默（通知失败不影响派发）。
    """
    dep_ids = task_dependencies(task)
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
        for up in sorted(rows, key=lambda x: task_number(x) or 0):
            no = task_number(up)
            label = f"#T-{no}" if no else up.id[:8]
            result = task_last_result(up) or ""
            lines.append(
                f"- {label}「{(task_title(up) or '')[:40]}」结论：{result[:300]}"
            )
            for a in arts_by_task.get(up.id, [])[:3]:
                lines.append(
                    f"  · 产物：{getattr(a, 'file_path', '') or getattr(a, 'name', '')}"
                )
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
    dispatch_start = time.monotonic()
    while True:
        t0 = time.monotonic()
        due = await TaskQueueService.claim_due_tasks()
        claim_dt = time.monotonic() - t0
        if due:
            logger.info(
                "[DutyDispatcher] claim_due_tasks found %d task(s) in %.3fs",
                len(due),
                claim_dt,
            )
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
            await _maybe_publish_queue_drained(len(attempted))
            logger.info(
                "[DutyDispatcher] dispatch_due_tasks returning after %.3fs (attempted %d)",
                time.monotonic() - dispatch_start,
                len(attempted),
            )
            return
        attempted.add(t.id)

        # growth 适配器特权分支已退役（阶段九.6：growth 流水线迁通用轮次
        # 机制，阶段任务=普通 pending 任务走标准 duty 派发），无任何
        # task_data 驱动的执行路径分叉。

        project_id = t.project_id or 0
        category = task_category(t) or "default"
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
        if task_dispatch_count(claimed) >= DISPATCH_CLAIM_CIRCUIT_LIMIT:
            await TaskQueueService.advance_task(
                t.id,
                "failed",
                result=(
                    f"值守派发熔断：{DISPATCH_CLAIM_CIRCUIT_LIMIT} 次派发未推进"
                    "任务终态（未 take/未 update_status）"
                ),
                by="system",
                thread_id=claimed.last_thread_id,
            )
            continue

        # duty runs have no host page: 域解析 profile-first → L1 域标注兜底
        # （与文本消息路径同源；此前值守漏接 L1，跨项目任务首轮全量）
        domain, hint_reason = await resolve_wakeup_domain(project_id, t.description or "")

        # 跨任务产出传递：依赖任务的结论摘要与产物链接注入唤醒 payload——
        # 链式任务的执行者（独立 wakeup 线程）拿不到上游 thread 的消息，
        # 缺了这段它只能重新调研或编造（链式任务的命脉）。
        instruction_text = t.description or ""
        assigned_skills = task_skills(t)
        if assigned_skills:
            canonical_names = []
            try:
                from app.core.learning.skills.discovery import skill_discovery

                for s_name in assigned_skills:
                    match, rel, _ = await skill_discovery.exact_search(s_name)
                    canonical_names.append(rel[0].name if (match and rel) else s_name)
            except Exception:
                canonical_names = assigned_skills
            skills_str = ", ".join(canonical_names)
            first_skill = canonical_names[0]
            skill_guide = (
                f"【专用技能指引】：本任务已关联专用技能 [{skills_str}]。"
                f"请在执行前优先调用 skill(\"{first_skill}\") 获取工具命令与执行路由，严禁自行编写并调试原生爬虫或临时脚本。\n\n"
            )
            instruction_text = skill_guide + instruction_text
        upstream_note = await _build_upstream_context(t)
        if upstream_note:
            instruction_text = f"{instruction_text}\n\n{upstream_note}"

        # 任务描述即第一条 human 消息的全文（不经模板包装）；任务元信息
        # （id/风险档/截止/评审反馈）走系统提示词层（main.duty.task.txt，
        # 经 metadata.duty_task 注入，prompts.py 渲染）。
        try:
            t0 = time.monotonic()
            result = await dispatch_agent_run(
                thread_id=thread_id,
                message_content=instruction_text,
                # pid=0（工作空间任务）是合法值，勿用 `or None` 短路——
                # 0 → None 会击穿 ConversationCreatedEvent 的 int 校验，
                # 导致 drain failed 循环（2026-09-22 实测事故）。
                project_id=project_id,
                member_id=await TaskQueueService.resolve_member_id(t),
                # source 必须显式传：dispatch_agent_run 的独立参数（默认
                # None），USER_PROMPT_SUBMIT hook 依赖它跳过兜底 L1 域分类
                # ——漏传会让 hook 按措辞猜域，把任务误装进项目受限
                # profile（2026-09-23 实测事故第二注入点）。
                source="duty",
                metadata={
                    "source": "duty",
                    "source_task_id": t.id,
                    "channel_name": str((t.source_ref or {}).get("channel") or ""),
                    "goal_prefix": "[Wakeup] ",
                    "duty_task": {
                        "id": t.id,
                        "status": t.status,
                        "title": task_title(t) or "",
                        "priority": task_priority(t),
                        "risk": t.risk_level or "T3",
                        "due": (t.due_at or t.next_run_at).isoformat()
                        if (t.due_at or t.next_run_at)
                        else "now",
                        "category": category,
                        "skills": assigned_skills,
                        "feedback": (t.acceptance or {}).get("feedback") or "",
                    },
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
        logger.info(
            "[DutyDispatcher] dispatch_agent_run prepared in %.3fs (status=%s)",
            time.monotonic() - t0,
            result.status,
        )
        if result.status == DispatchStatus.FAILED:
            logger.error(
                f"[DutyDispatcher] wakeup dispatch failed for task {t.id}: {result.error}"
            )
            # 派发失败：回滚认领（pending），60s 兜底重试；连续失败由熔断收敛。
            await TaskQueueService.release_dispatch_claim(t.id, thread_id)
            return  # avoid tight-loop redispatching a broken dispatch
        if not result.inputs:
            # QUEUED 但 inputs 为空 = 派发内部异常吞掉了错误：任务已认领却
            # 永远不会 run（无日志悬挂 in_progress，只能等 reconciler 收尸）。
            # 显式失败并回滚认领，把问题炸出来而不是静默丢任务。
            logger.error(
                f"[DutyDispatcher] wakeup dispatch returned empty inputs for task {t.id} "
                f"(status={result.status}, error={result.error}) — releasing claim"
            )
            await TaskQueueService.release_dispatch_claim(t.id, thread_id)
            return
        if result.inputs:
            logger.info(
                f"[DutyDispatcher] wakeup run started (task={t.id}, thread={thread_id})"
            )
            t0 = time.monotonic()
            async with _wakeup_run_semaphore:
                await _run_wakeup_with_deadline(thread_id, result.inputs)
            logger.info(
                "[DutyDispatcher] wakeup run finished in %.3fs (task=%s)",
                time.monotonic() - t0,
                t.id,
            )
            # loop continues: run finished (or HITL-suspended) -> claim next
