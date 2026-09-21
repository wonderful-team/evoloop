"""Task queue service — autonomous task loop stage 1.

Queue semantics on top of the existing ProjectTask table (SSOT).
System principle: the queue only stores and orders; decomposition
(plans, subtasks, immediate actions) belongs to the Agent at runtime.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import func, select, update

from app.domain.tasks.constants import (
    PRIORITY_ORDER,
    QUEUE_TRANSITIONS,
    REQUEUE_LIMIT,
    RESULT_MAX,
    WORKFLOW_RETRY_DELAY_SECONDS,
    WORKFLOW_RETRY_LIMIT,
)
from app.domain.tasks.events import publish_task_queue_event
from app.domain.tasks.runtime.wakeup import notify_duty_wakeup
from app.infrastructure.database.sql.database import session_scope
from app.models.project import ProjectTask
from app.utils.id import gen_uuid
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


def _dispatch_order_key(t: ProjectTask):
    """Dispatch/list ordering: priority → due time → category."""
    td = t.task_data or {}
    prio = PRIORITY_ORDER.get(str(td.get("priority")), 2)
    due = t.due_at or t.next_run_at
    if due is not None and due.tzinfo is None:
        # sqlite 常回 naive UTC；统一挂上 UTC 与 aware 值比较
        due = due.replace(tzinfo=timezone.utc)
    return (prio, due or _now(), str(td.get("category") or ""))
class TaskQueueError(Exception):
    pass


class EventSpecError(Exception):
    """外部事件 spec 缺必填字段（payload malformed，非队列状态机错误）。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_result(text: str | None) -> str | None:
    if text is None:
        return None
    return text[:RESULT_MAX]



class TaskQueueService:
    """DB-as-queue operations over ProjectTask. All writes are status-machine guarded."""

    @staticmethod
    async def ingest_event(
        source_system: str, event_id: str, spec: dict[str, Any]
    ) -> tuple[ProjectTask, bool]:
        """外部系统消息 → 任务入队（external 入口的全部队列语义）。

        消息经 channel 层归一化（``notifications/mcp_message`` →
        InboundMessageEvent）后进入此处；本层只做三件事：spec 校验、
        幂等（dedup_key = "{source}:{event_id}"）、以 source=external
        落任务（胖 payload，引擎不解释业务）。
        ``contact`` 为会话类消息的回复路由元数据，随 source_ref 落库。
        """
        from app.domain.tasks.constants import INGESTION_REQUIRED_FIELDS

        for field in INGESTION_REQUIRED_FIELDS:
            if not str(spec.get(field) or "").strip():
                raise EventSpecError(f"spec missing required field: {field}")

        dedup_key = f"{source_system}:{event_id}"
        existing = await TaskQueueService.get_by_dedup_key(dedup_key)
        if existing is not None:
            return existing, False  # 幂等重投

        start_hours = spec.get("start_in_hours")
        due_at = (
            utcnow() + timedelta(hours=float(start_hours))
            if start_hours is not None
            else None
        )

        contact = str(spec.get("contact") or "").strip() or None
        channel = str(spec.get("channel") or "").strip() or None
        source_ref: dict[str, Any] = {
            "kind": "event",
            "source_system": source_system,
            "event_id": event_id,
        }
        if contact:
            source_ref["contact"] = contact
        if channel:
            source_ref["channel"] = channel

        task = await TaskQueueService.create_task(
            project_id=int(spec.get("project_id") or 0),
            title=str(spec["title"]),
            description=str(spec.get("description") or ""),
            source="external",
            source_ref=source_ref,
            category=spec.get("category"),
            priority=str(spec.get("priority") or "medium"),
            risk_level=spec.get("risk_level"),
            due_at=due_at,
            dedup_key=dedup_key,
        )
        return task, True

    @staticmethod
    async def create_task(
        *,
        project_id: int,
        title: str,
        description: str = "",
        type: Literal["once", "recurring"] = "once",
        source: str = "user",
        source_ref: dict[str, Any] | None = None,
        category: str | None = None,
        priority: str = "medium",
        risk_level: str | None = None,
        due_at: datetime | None = None,
        trigger_spec: str | None = None,
        dedup_key: str | None = None,
        member_id: int = 0,
        parent_id: str | None = None,
        dependencies: list[str] | None = None,
    ) -> ProjectTask:
        """Insert a task row. Entry semantics:
        - source=user → pending (user-planned, accepted as-is)
        - source=agent → proposed (needs user confirmation; T3/T4 may auto-confirm)
        - source=external → pending; dedup_key enforced (None duplicate raises ValueError)
        """
        if source not in ("user", "agent", "external"):
            raise TaskQueueError(f"invalid source: {source}")
        if dedup_key:
            existing = await TaskQueueService.get_by_dedup_key(dedup_key)
            if existing is not None:
                return existing  # idempotent re-delivery (any source)

        status = "proposed" if source == "agent" else "pending"
        if trigger_spec:
            type = "recurring"
        trigger = trigger_spec
        next_run_at = None
        if trigger:
            from app.infrastructure.scheduler.service import SchedulerService

            next_run_at = SchedulerService.calculate_next_run(trigger, _now())
        task_data: dict[str, Any] = {
            "title": title,
            "priority": priority,
        }
        if category:
            task_data["category"] = category
        if dependencies is not None:
            task_data["dependencies"] = dependencies
        # 短编号：项目内递增，对话/评审/反馈用 "#T-<n>" 指代（uuid 太重）
        origin_thread_id = str((source_ref or {}).get("ref") or "") or None
        async with session_scope() as session:
            max_no = await session.execute(
                select(func.coalesce(func.max(ProjectTask.task_no), 0)).where(
                    ProjectTask.project_id == project_id
                )
            )
            task_no = int(max_no.scalar() or 0) + 1
            task_data["task_no"] = task_no
            task = ProjectTask(
                id=gen_uuid(),
                project_id=project_id,
                member_id=member_id,
                parent_id=parent_id,
                status=status,
                progress=0,
                description=description or None,
                type=type,
                task_data=task_data,
                source=source,
                source_ref=source_ref or {},
                task_no=task_no,
                origin_thread_id=origin_thread_id,
                risk_level=risk_level,
                due_at=due_at,
                trigger_spec=trigger,
                dedup_key=dedup_key,
                next_run_at=next_run_at,
            )
            session.add(task)
            await session.flush()
        notify_duty_wakeup()
        await publish_task_queue_event(task, event="task_created")
        return task

    @staticmethod
    async def get_by_dedup_key(dedup_key: str) -> ProjectTask | None:
        from sqlalchemy import select

        async with session_scope() as session:
            stmt = select(ProjectTask).where(
                ProjectTask.dedup_key == dedup_key
            )
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    @staticmethod
    async def get_task_by_thread(thread_id: str) -> ProjectTask | None:
        """按运行线程反查任务（任务认领时落 last_thread_id，见 take）。

        回复路由用：wakeup 会话终态 → 任务 → source_ref 回复元数据。
        """
        from sqlalchemy import select

        async with session_scope() as session:
            stmt = select(ProjectTask).where(
                ProjectTask.last_thread_id == thread_id
            )
            res = await session.execute(stmt)
            return res.scalars().first()

    @staticmethod
    async def get_task(task_id: str) -> ProjectTask | None:
        async with session_scope() as session:
            stmt = select(ProjectTask).where(ProjectTask.id == task_id)
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    @staticmethod
    async def get_subtasks_counts(parent_ids: list[str]) -> dict[str, dict[str, int]]:
        """Return {parent_id: {'total': N, 'completed': M}} for given parent task IDs."""
        if not parent_ids:
            return {}
        async with session_scope() as session:
            stmt = select(ProjectTask.parent_id, ProjectTask.status).where(
                ProjectTask.parent_id.in_(parent_ids)
            )
            res = await session.execute(stmt)
            counts: dict[str, dict[str, int]] = {
                pid: {"total": 0, "completed": 0} for pid in parent_ids
            }
            for pid, status in res.all():
                if pid and pid in counts:
                    counts[pid]["total"] += 1
                    if status == "completed":
                        counts[pid]["completed"] += 1
            return counts

    @staticmethod
    async def list_tasks(
        *,
        project_id: int | None = None,
        status: str | None = None,
        category: str | None = None,
        source: str | None = None,
        due_before: datetime | None = None,
        root_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ProjectTask]:

        async with session_scope() as session:
            stmt = select(ProjectTask)
            if project_id is not None:
                stmt = stmt.where(ProjectTask.project_id == project_id)
            if status:
                stmt = stmt.where(ProjectTask.status == status)
            if source:
                stmt = stmt.where(ProjectTask.source == source)
            if due_before is not None:
                stmt = stmt.where(
                    (ProjectTask.due_at <= due_before)
                    | (ProjectTask.next_run_at <= due_before)
                )
            if root_only:
                stmt = stmt.where(ProjectTask.parent_id.is_(None))
            rows = (await session.execute(stmt)).scalars().all()
        if category:
            rows = [r for r in rows if (r.task_data or {}).get("category") == category]

        rows.sort(key=_dispatch_order_key)
        return rows[offset:offset + limit] if offset else rows[:limit]

    @staticmethod
    async def take_task(task_id: str, thread_id: str) -> ProjectTask:
        """Claim a pending task for execution (atomic pending→in_progress).

        派发即认领（claim-then-persist）下，dispatcher 已在派发前完成系统侧
        认领并绑定同一 wakeup 线程——agent 的 take 变为幂等确认：同线程重复
        take 直接返回已认领任务；跨线程占用仍然拒绝。
        """
        current = await TaskQueueService.get_task(task_id)
        if current is not None and current.status == "in_progress":
            if (current.last_thread_id or "") == thread_id:
                return current  # 幂等：系统认领即绑定，无事件重复发布
            raise TaskQueueError(
                f"task {task_id} is already in progress on another thread"
            )

        async with session_scope() as session:
            stmt = (
                update(ProjectTask)
                .where(ProjectTask.id == task_id, ProjectTask.status == "pending")
                .values(status="in_progress", last_thread_id=thread_id)
            )
            res = await session.execute(stmt)
            if res.rowcount == 0:
                raise TaskQueueError(
                    f"task {task_id} is not claimable (not pending or already taken)"
                )
        task = await TaskQueueService.get_task(task_id)
        assert task is not None
        await publish_task_queue_event(task, event="task_taken")
        return task

    @staticmethod
    async def claim_for_dispatch(task_id: str, thread_id: str) -> ProjectTask | None:
        """System-side claim at dispatch (pending→in_progress, atomic).

        派发即认领：one-shot 任务派发前落持久化占位（in_progress + 绑线程
        + dispatch_count 递增），与 recurring「认领即推进 next_run_at」对齐。
        修复「run 完成 × 任务仍 pending」被 DutyWakeupSubscriber 立即重派发
        的紧派发环。认领失败（并发/状态已变）返回 None，调用方跳过本轮。

        发布 ``task_taken``：认领即绑定时刻，前端看板语义与原 agent take 一致。
        """
        task = await TaskQueueService.get_task(task_id)
        if task is None:
            return None
        td = dict(task.task_data or {})
        td["dispatch_count"] = int(td.get("dispatch_count") or 0) + 1
        async with session_scope() as session:
            res = await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == task_id, ProjectTask.status == "pending")
                .values(status="in_progress", last_thread_id=thread_id, task_data=td)
            )
            if res.rowcount == 0:
                return None
        claimed = await TaskQueueService.get_task(task_id)
        assert claimed is not None
        await publish_task_queue_event(claimed, event="task_taken")
        return claimed

    @staticmethod
    async def release_dispatch_claim(task_id: str, thread_id: str) -> None:
        """Rollback a dispatch claim (in_progress→pending) when dispatch failed.

        派发失败（DispatchStatus.FAILED / 派发异常）时回滚认领占位，任务回到
        队列由下一拍重试；``dispatch_count`` 保留——累计到
        ``DISPATCH_CLAIM_CIRCUIT_LIMIT`` 由熔断强制终态。不 notify_duty_wakeup：
        派发失败是确定性问题，立即重试只会形成无意义热循环，60s 兜底即可。
        """
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(
                    ProjectTask.id == task_id,
                    ProjectTask.status == "in_progress",
                    ProjectTask.last_thread_id == thread_id,
                )
                .values(status="pending", last_thread_id=None)
            )

    @staticmethod
    async def advance_task(
        task_id: str,
        status: str,
        *,
        result: str | None = None,
        self_check: dict[str, Any] | None = None,
        by: str = "agent",
    ) -> ProjectTask:
        """Move a task forward through the status machine.

        ``by`` marks the caller: "agent" (duty run) or "user" (board/confirm
        API). Proposals are only confirmable by the user — the executor run
        must never confirm its own proposal.
        """
        current = await TaskQueueService.get_task(task_id)
        if current is None:
            raise TaskQueueError(f"task {task_id} not found")
        cur = current.status
        # 执行权隔离：提案的确认是用户决策（confirm API），Agent 只能推进
        if cur == "proposed" and by != "user":
            raise TaskQueueError("proposed tasks are confirmed by the user, not the agent")
        # completed 必须留痕：干了什么、结果如何（先于转移合法性，错误信息更有用）
        if status == "completed" and not (result or "").strip():
            raise TaskQueueError("completed requires result (what was done, outcome)")
        if status not in QUEUE_TRANSITIONS.get(cur, ()):
            raise TaskQueueError(f"illegal transition {cur} → {status}")

        # Acceptance pre-authorization on self-check (Agent reports done):
        # - T3/T4 with an origin conversation: NOT auto-completed — the result
        #   is pushed back to the origin dialogue for the reviewer (原对话
        #   Agent) to audit (reviewer:auto verdict drives completion). A
        #   waiting_acceptance row with task_data.review_pending=1 is "awaiting
        #   reviewer", distinct from T1/T2 human acceptance.
        # - No origin thread (board-created / workflow tasks): system
        #   auto-completes as before (no reviewer context to consult).
        # - T1/T2: waiting_acceptance (human decides).
        # self_checked is therefore a transient state, never persisted.
        effective = status
        review_requested = False
        if status == "self_checked":
            if current.trigger_spec:
                # recurring task: this round is done, requeue for next trigger
                effective = "pending"
            else:
                risk = current.risk_level or "T3"
                has_origin = bool(current.origin_thread_id)
                # requires_human_signoff：方向性决策产出（选品方向/定价/上架
                # 放行等）——评审者只能核验"做没做对"，不能替用户做商业判断，
                # 此类任务执行完挂"待人工验收"（与 T1/T2 同语义），人批准才
                # 解锁下游。
                needs_signoff = bool(
                    (current.task_data or {}).get("requires_human_signoff")
                )
                if risk in ("T3", "T4"):
                    if has_origin and not needs_signoff:
                        effective = "waiting_acceptance"
                        review_requested = True
                    else:
                        effective = "waiting_acceptance" if (needs_signoff or risk in ("T1", "T2")) else "completed"
                else:
                    effective = "waiting_acceptance"

        values: dict[str, Any] = {"status": effective}
        if result is not None:
            values["task_data"] = {
                **(current.task_data or {}),
                "last_result": _clamp_result(result),
            }
        if review_requested:
            values["task_data"] = {
                **(values["task_data"]),
                "review_pending": True,
            }
        if self_check is not None:
            values["self_check"] = self_check
        if effective != status and not review_requested:
            values["acceptance"] = {
                "by": "system:auto",
                "at": _now().isoformat(),
                "verdict": "accepted",
                "risk": current.risk_level,
            }
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask).where(ProjectTask.id == task_id).values(**values)
            )
        if effective != status:
            # recurring 自检回队：立即唤醒 supervisor 接续下一轮
            notify_duty_wakeup()
        updated = await TaskQueueService.get_task(task_id)
        assert updated is not None
        await publish_task_queue_event(
            updated,
            event="task_advanced",
            extra={"requested_status": status, "effective_status": effective},
        )
        if review_requested:
            # 值守完成 → 回灌原对话，交由创建任务时的对话 Agent（评审者）
            # 以用户立场核验。异步触发，不阻塞 update_status 返回。
            from app.domain.tasks.review import trigger_review

            await trigger_review(updated)
        elif effective == "waiting_acceptance" and not review_requested:
            # signoff / T1/T2 等人拍板 → 推送手机触达（否则用户不开看板就
            # 无从知道链路停在自己这里）
            try:
                from app.core.channel.base import ChannelContext
                from app.core.channel.output.mobile_channel import MobileChannel
                from app.core.config import settings as _settings

                if _settings.MOBILE_SYNC_ENABLED:
                    no = (updated.task_data or {}).get("task_no")
                    label = f"#T-{no}" if no else updated.id[:8]
                    title = (updated.task_data or {}).get("title", "")
                    await MobileChannel().send_hitl_request(
                        request_id=updated.id,
                        request_type="confirmation",
                        prompt=f"任务 {label}「{title[:40]}」执行完成，等你拍板（在看板验收，批准后链路继续）",
                        ctx=ChannelContext(thread_id=updated.origin_thread_id or updated.id, project_id=updated.project_id),
                        metadata={"kind": "task_signoff", "task_id": updated.id},
                    )
            except Exception:
                logger.exception("[TaskQueue] signoff mobile push failed")
        return updated

    @staticmethod
    async def find_review_pending_by_thread(origin_thread_id: str):
        """Task awaiting its reviewer verdict on the given origin thread."""
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope

        async with session_scope() as session:
            stmt = (
                select(ProjectTask)
                .where(
                    ProjectTask.origin_thread_id == origin_thread_id,
                    ProjectTask.status == "waiting_acceptance",
                )
                .order_by(ProjectTask.task_no.desc())
                .limit(1)
            )
            row = await session.execute(stmt)
            task = row.scalars().first()
        if task is None:
            return None
        if not (task.task_data or {}).get("review_pending"):
            return None
        return task

    @staticmethod
    async def submit_acceptance(
        task_id: str, *, by: str, verdict: Literal["accepted", "rejected"], feedback: str = ""
    ) -> ProjectTask:
        """User acceptance. accepted → completed; rejected → pending (requeued).

        Rejected tasks carry the verdict + feedback in ``acceptance`` (surfaced
        to the Agent via `tasks list` and the wakeup payload) and re-enter the
        queue — the rework loop goes through dispatch, never stranded in
        in_progress.
        """
        task = await TaskQueueService.get_task(task_id)
        if task is None:
            raise TaskQueueError(f"task {task_id} not found")
        if task.status != "waiting_acceptance":
            raise TaskQueueError(
                f"task {task_id} not in waiting_acceptance (is {task.status})"
            )
        receipt = {"by": by, "at": _now().isoformat(), "verdict": verdict, "feedback": feedback}
        target = "completed" if verdict == "accepted" else "pending"

        # 评审收敛纪律：reviewer 不通过最多 2 轮。第 2 轮仍不通过 → 任务转
        # failed 并升级原对话"转人工仲裁"，杜绝"评审-返工"无限循环导致的
        # 执行者过度实施。人工（user）拒绝不受此限——用户的裁决权优先。
        if verdict == "rejected" and target == "pending":
            new_count = int(getattr(task, "review_count", 0) or 0) + 1
            if by.startswith("reviewer:") and new_count >= 2:
                target = "failed"
                receipt["escalated"] = True
            values_extra: dict[str, Any] = {}
            if by.startswith("reviewer:"):
                values_extra["review_count"] = new_count
        else:
            values_extra = {}

        async with session_scope() as session:
            values = {"acceptance": receipt, "status": target, **values_extra}
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == task_id)
                .values(**values)
            )
        if verdict == "rejected":
            if target == "failed":
                # 两轮评审未通过：升级原对话转人工仲裁（终态，不再回队）
                updated = await TaskQueueService.get_task(task_id)
                assert updated is not None
                from app.domain.tasks.review import notify_arbitration

                await notify_arbitration(updated, feedback)
                await publish_task_queue_event(
                    updated, event="task_rejected", extra={"by": by, "feedback": feedback}
                )
                return updated
            notify_duty_wakeup()
        updated = await TaskQueueService.get_task(task_id)
        assert updated is not None
        await publish_task_queue_event(
            updated,
            event="task_accepted" if verdict == "accepted" else "task_rejected",
            extra={"by": by, "feedback": feedback},
        )
        return updated

    @staticmethod
    async def resolve_member_id(task: ProjectTask) -> int:
        """多租户 fail-closed 的任务归属解析：task.member_id → repositories 回填。

        Project 无 SQL 模型（文件制），归属映射在 repositories 表
        （Repository.project_id → Repository.member_id）。单租户模式下
        member_id 恒 0，回填结果不影响。
        """
        if task.member_id:
            return int(task.member_id)
        from sqlalchemy import select

        from app.infrastructure.database.sql.database import session_scope
        from app.models.codebase import Repository

        async with session_scope() as session:
            result = await session.execute(
                select(Repository.member_id).where(
                    Repository.project_id == (task.project_id or 0)
                )
            )
            member_id = result.scalar_one_or_none()
            return int(member_id or 0)

    @staticmethod
    async def dashboard(project_id: int | None = None):
        """看板聚合（原 API 路由内的业务逻辑归位 service 层）。"""
        from datetime import timedelta

        from sqlalchemy import func, select

        from app.domain.tasks.schemas import DashboardPayload
        from app.models import HumanRequest
        from app.models.conversation import AgentActivity
        from app.utils.time import utcnow

        activity_filter: list[Any] = []
        if project_id is not None:
            project_thread_ids = select(ProjectTask.last_thread_id).where(
                ProjectTask.project_id == project_id,
                ProjectTask.last_thread_id.isnot(None),
            )
            activity_filter = [AgentActivity.thread_id.in_(project_thread_ids)]

        counts: dict[str, int] = {}
        async with session_scope() as session:
            stmt = select(ProjectTask.status, func.count(ProjectTask.id)).group_by(
                ProjectTask.status
            )
            if project_id is not None:
                stmt = stmt.where(ProjectTask.project_id == project_id)
            rows = await session.execute(stmt)
            for st, n in rows:
                counts[st] = int(n)

        # duty state: busy if any task in_progress; error if failed in last 24h
        from app.core.channel.duty.config import load_global_duty_config

        duty_enabled = bool(load_global_duty_config().get("enabled"))
        duty_state = "idle"
        if counts.get("in_progress", 0) > 0:
            duty_state = "busy"
        async with session_scope() as session:
            since = utcnow() - timedelta(hours=24)
            failed_recent = await session.execute(
                select(func.count(ProjectTask.id)).where(
                    ProjectTask.status == "failed",
                    ProjectTask.updated_at >= since,
                    *(
                        [ProjectTask.project_id == project_id]
                        if project_id is not None
                        else []
                    ),
                )
            )
            if int(failed_recent.scalar() or 0) > 0:
                duty_state = "error"

        # tokens: today + this week from agent_activities (per-run rollup)
        week_tokens = {"input": 0, "output": 0, "llm_calls": 0}
        current_run = None
        today_window: dict[str, Any] = {"since": None, "until": None}
        async with session_scope() as session:
            now = utcnow()
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = day_start - timedelta(days=now.weekday())
            base = select(
                func.coalesce(func.sum(AgentActivity.input_tokens), 0),
                func.coalesce(func.sum(AgentActivity.output_tokens), 0),
                func.coalesce(func.sum(AgentActivity.llm_calls), 0),
            ).where(
                AgentActivity.updated_at >= week_start,
                *activity_filter,
            )
            res = await session.execute(
                base.where(AgentActivity.updated_at >= day_start)
            )
            r = res.one()
            today_tokens = {"input": int(r[0]), "output": int(r[1]), "llm_calls": int(r[2])}
            r = await session.execute(base)
            r = r.one()
            week_tokens = {"input": int(r[0]), "output": int(r[1]), "llm_calls": int(r[2])}
            # today active window (approximate work span): min/max activity time
            win = await session.execute(
                select(
                    func.min(AgentActivity.updated_at),
                    func.max(AgentActivity.updated_at),
                ).where(
                    AgentActivity.updated_at >= day_start,
                    *activity_filter,
                )
            )
            w = win.one()
            today_window = {
                "since": w[0].isoformat() if w[0] else None,
                "until": w[1].isoformat() if w[1] else None,
            }
            fresh_cutoff = utcnow() - timedelta(hours=2)
            running = await session.execute(
                select(AgentActivity).where(
                    AgentActivity.status == "running",
                    AgentActivity.updated_at >= fresh_cutoff,
                    *activity_filter,
                )
            )
            act = running.scalars().first()
            if act:
                current_run = {
                    "thread_id": act.thread_id,
                    "goal": (act.main_goal or "")[:80],
                    "started_at": act.updated_at.isoformat() if act.updated_at else None,
                    "input_tokens": int(act.input_tokens or 0),
                    "output_tokens": int(act.output_tokens or 0),
                }

        # 7-day daily aggregation for charts (tokens + completed tasks)
        daily_days: list[dict[str, Any]] = []
        async with session_scope() as session:
            now = utcnow()
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_ago = day_start - timedelta(days=6)
            tok_rows = await session.execute(
                select(
                    func.date(AgentActivity.updated_at).label("d"),
                    func.coalesce(func.sum(AgentActivity.input_tokens), 0),
                    func.coalesce(func.sum(AgentActivity.output_tokens), 0),
                )
                .where(AgentActivity.updated_at >= week_ago)
                .where(*activity_filter)
                .group_by(func.date(AgentActivity.updated_at))
            )
            tok_map = {
                str(r[0]): {"input": int(r[1]), "output": int(r[2])}
                for r in tok_rows
            }
            done_rows = await session.execute(
                select(
                    func.date(ProjectTask.updated_at).label("d"),
                    func.count(ProjectTask.id),
                )
                .where(
                    ProjectTask.status == "completed",
                    ProjectTask.updated_at >= week_ago,
                    *(
                        [ProjectTask.project_id == project_id]
                        if project_id is not None
                        else []
                    ),
                )
                .group_by(func.date(ProjectTask.updated_at))
            )
            done_map = {str(r[0]): int(r[1]) for r in done_rows}
            for i in range(7):
                d = (week_ago + timedelta(days=i)).date()
                key = d.isoformat()
                tk = tok_map.get(key, {"input": 0, "output": 0})
                daily_days.append(
                    {
                        "date": key,
                        "input_tokens": tk["input"],
                        "output_tokens": tk["output"],
                        "completed": done_map.get(key, 0),
                    }
                )

        # event feed: recently touched tasks (newest first, max 10)
        recent_events: list[dict[str, Any]] = []
        async with session_scope() as session:
            stmt = select(ProjectTask).order_by(ProjectTask.updated_at.desc()).limit(10)
            if project_id is not None:
                stmt = stmt.where(ProjectTask.project_id == project_id)
            else:
                stmt = stmt.where(ProjectTask.project_id.isnot(None))
            for t in (await session.execute(stmt)).scalars().all():
                td = t.task_data or {}
                recent_events.append(
                    {
                        "at": t.updated_at.isoformat() if t.updated_at else None,
                        "kind": (
                            "proposal"
                            if t.status == "proposed"
                            else "acceptance"
                            if t.acceptance
                            else "progress"
                        ),
                        "title": td.get("title"),
                        "status": t.status,
                        "task_id": t.id,
                        "result": (td.get("last_result") or "")[:120],
                    }
                )

        # awaiting_human: 挂起等人工决策的任务（线程上有 pending HumanRequest）
        # —— 值守信任纪律的可见性面：问人必须被看见、被回答。
        awaiting_human: list[dict[str, Any]] = []
        async with session_scope() as session:
            busy_tasks = (
                await session.execute(
                    select(ProjectTask).where(
                        ProjectTask.status == "in_progress",
                        ProjectTask.last_thread_id.isnot(None),
                        *(
                            [ProjectTask.project_id == project_id]
                            if project_id is not None
                            else []
                        ),
                    )
                )
            ).scalars().all()
            if busy_tasks:
                thread_ids = [t.last_thread_id for t in busy_tasks]
                pending_reqs = (
                    await session.execute(
                        select(HumanRequest)
                        .where(
                            HumanRequest.status == "pending",
                            HumanRequest.thread_id.in_(thread_ids),
                        )
                        .order_by(HumanRequest.created_at.desc())
                    )
                ).scalars().all()
                req_by_thread: dict[str, HumanRequest] = {}
                for req in pending_reqs:
                    req_by_thread.setdefault(req.thread_id, req)
                for t in busy_tasks:
                    req = req_by_thread.get(t.last_thread_id or "")
                    if req is None:
                        continue
                    awaiting_human.append(
                        {
                            "task_id": t.id,
                            "title": (t.task_data or {}).get("title"),
                            "thread_id": t.last_thread_id,
                            "question": (req.description or "")[:200],
                            "options": req.options or [],
                            "default_value": req.default_value,
                            "at": req.created_at.isoformat() if req.created_at else None,
                        }
                    )

        return DashboardPayload(
            counts=counts,
            duty_state=duty_state,
            duty_enabled=duty_enabled,
            tokens={"today": today_tokens, "week": week_tokens},
            today_window=today_window,
            current_run=current_run,
            daily=daily_days,
            recent_events=recent_events,
            awaiting_human=awaiting_human,
        )

    @staticmethod
    def require_in_project(task: ProjectTask, project_id: int | None) -> None:
        """项目隔离断言：task 必须属于 project_id（None = 全局模式不设限）。"""
        if project_id is not None and task.project_id != int(project_id):
            raise TaskQueueError(f"task {task.id} belongs to another project")

    @staticmethod
    async def requeue_stuck_task(task_id: str, reason: str) -> ProjectTask | None:
        """Reconcile move: park a stranded in_progress task back into the queue.

        Used by the duty supervisor when the run behind a task reached a
        terminal state without advancing the task (crash, lost run, agent
        dropped the ball). ``requeue_count`` in task_data bounds retries:
        after ``REQUEUE_LIMIT`` requeues the task fails with the reason
        recorded, so a poison task cannot loop forever.
        """
        task = await TaskQueueService.get_task(task_id)
        if task is None or task.status != "in_progress":
            return None
        td = dict(task.task_data or {})
        count = int(td.get("requeue_count") or 0) + 1
        td["requeue_count"] = count
        td["last_result"] = reason[:RESULT_MAX]
        target = "failed" if count > REQUEUE_LIMIT else "pending"
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == task_id)
                .values(task_data=td, status=target)
            )
        notify_duty_wakeup()
        return await TaskQueueService.get_task(task_id)

    @staticmethod
    async def requeue_workflow_task(task_id: str, reason: str) -> ProjectTask | None:
        """Requeue a failed workflow stage until its retry budget is exhausted."""
        task = await TaskQueueService.get_task(task_id)
        if task is None or task.status != "in_progress":
            return None
        task_data = dict(task.task_data or {})
        retry_count = int(task_data.get("workflow_retry_count") or 0) + 1
        task_data["workflow_retry_count"] = retry_count
        task_data["last_error"] = reason[:RESULT_MAX]
        task_data["last_result"] = f"retry {retry_count}: {reason}"[:RESULT_MAX]
        target = "failed" if retry_count > WORKFLOW_RETRY_LIMIT else "pending"
        values: dict[str, Any] = {"task_data": task_data, "status": target}
        if target == "pending":
            values["due_at"] = utcnow() + timedelta(seconds=WORKFLOW_RETRY_DELAY_SECONDS)
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask).where(ProjectTask.id == task_id).values(**values)
            )
        notify_duty_wakeup()
        return await TaskQueueService.get_task(task_id)

    @staticmethod
    async def claim_due_tasks(now: datetime | None = None) -> list[ProjectTask]:
        """Scan due tasks for dispatch, ordered by priority → due → category.

        - one-shot: status=pending AND (due_at IS NULL -> dispatchable
          immediately, OR due_at <= now when a start time was given)
        - recurring: trigger_spec set AND next_run_at <= now (advanced on
          claim; claim-then-persist prevents re-dispatch across restarts)
        - proposed / waiting_acceptance / terminal tasks are never dispatched.
        """

        now = now or _now()
        async with session_scope() as session:
            from sqlalchemy import and_, or_

            stmt = select(ProjectTask).where(
                ProjectTask.status == "pending",
                or_(
                    # one-shot（无 trigger_spec）：due_at IS NULL → 立即可派发，
                    # 或给定开始时间已到。recurring 的到期判定只能走 next_run_at
                    # 分支——due_at 恒为 NULL，若不限定 trigger_spec，该分支会
                    # 永远命中，next_run_at 门控形同虚设（2026-09-21 实测：
                    # 明天首跑的每日巡检被判"到期"，开闸后爆发式连跑）。
                    and_(
                        ProjectTask.trigger_spec.is_(None),
                        or_(
                            ProjectTask.due_at.is_(None),
                            ProjectTask.due_at <= now,
                        ),
                    ),
                    and_(
                        ProjectTask.trigger_spec.isnot(None),
                        ProjectTask.next_run_at <= now,
                    ),
                ),
            )
            rows = (await session.execute(stmt)).scalars().all()
            # claim: advance recurring next_run_at immediately (persist on scope exit)
            for t in rows:
                if t.trigger_spec:
                    from app.infrastructure.scheduler.service import SchedulerService

                    t.next_run_at = SchedulerService.calculate_next_run(t.trigger_spec, now)

            ready_rows: list[ProjectTask] = []
            for task in rows:
                task_data = task.task_data or {}
                dependencies = task_data.get("dependencies")
                if not task_data.get("workflow_id") or not dependencies:
                    ready_rows.append(task)
                    continue
                dependency_result = await session.execute(
                    select(ProjectTask.id, ProjectTask.status).where(
                        ProjectTask.id.in_(dependencies)
                    )
                )
                dependency_statuses = dict(dependency_result.all())
                if len(dependency_statuses) != len(set(dependencies)):
                    continue
                if any(status != "completed" for status in dependency_statuses.values()):
                    continue
                ready_rows.append(task)
            rows = ready_rows

        # 值守开关接管（分闸，opt-in）：仅 customer_service_duty.enabled=true
        # 的项目派发；false/未配置/无本地路径均不派发（任务保持 pending，
        # 开启值守后自动恢复）。与 load_duty_config 自身缺省语义一致。
        # 例外：project_id=0 = 工作空间任务（无"项目参与"概念），不受分闸
        # 约束，只受托盘总闸约束（dispatcher 的全局总闸检查）。
        if rows:
            from app.core.channel.duty.config import load_duty_config

            by_project: dict[int, list[ProjectTask]] = {}
            for t in rows:
                by_project.setdefault(t.project_id or 0, []).append(t)
            rows = []
            for pid, group in by_project.items():
                if pid == 0:
                    rows.extend(group)
                    continue
                cfg = await load_duty_config(pid)
                if not cfg or not cfg.get("enabled"):
                    logger.info(
                        "[TaskQueue] project %s 值守未启用，挂起 %d 个到期任务",
                        pid,
                        len(group),
                    )
                    continue
                rows.extend(group)

        return sorted(rows, key=_dispatch_order_key)

    @staticmethod
    async def edit_task(
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        risk_level: str | None = None,
        task_type: str | None = None,
        due_at: datetime | None = None,
        clear_due_at: bool = False,
        trigger_spec: str | None = None,
        clear_trigger_spec: bool = False,
        cancel: bool = False,
    ) -> ProjectTask:
        """User-facing edit: field updates + optional cancel.

        Cancel is the only status move allowed to the user (all other status
        transitions stay system-driven); setting trigger_spec implies recurring.
        """
        task = await TaskQueueService.get_task(task_id)
        if task is None:
            raise TaskQueueError(f"task {task_id} not found")

        updates: dict[str, Any] = {}
        if cancel and task.status not in ("completed", "failed", "cancelled"):
            updates["status"] = "cancelled"

        td = dict(task.task_data or {})
        if title is not None:
            td["title"] = title
        if priority is not None:
            td["priority"] = priority
        if td != (task.task_data or {}):
            updates["task_data"] = td
        if description is not None:
            updates["description"] = description
        if risk_level is not None:
            updates["risk_level"] = risk_level
        if task_type is not None:
            updates["type"] = task_type
        if due_at is not None:
            if due_at <= _now():
                raise TaskQueueError("due_at must be in the future")
            updates["due_at"] = due_at
        elif clear_due_at:
            updates["due_at"] = None
        if trigger_spec is not None:
            updates["trigger_spec"] = trigger_spec
            updates["type"] = "recurring"
            from app.infrastructure.scheduler.service import SchedulerService

            updates["next_run_at"] = SchedulerService.calculate_next_run(
                trigger_spec, _now()
            )
        elif clear_trigger_spec:
            updates["trigger_spec"] = None
            updates["next_run_at"] = None
            updates["type"] = task_type or "once"

        if not updates:
            raise TaskQueueError("nothing to update")

        async with session_scope() as session:
            await session.execute(
                update(ProjectTask).where(ProjectTask.id == task_id).values(**updates)
            )
        updated = await TaskQueueService.get_task(task_id)
        assert updated is not None
        await publish_task_queue_event(updated, event="task_updated")
        return updated
