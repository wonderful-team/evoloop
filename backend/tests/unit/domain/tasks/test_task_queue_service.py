"""TaskQueueService unit tests — status machine, CAS take, claim grouping."""

from __future__ import annotations

import asyncio
import json as _json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import update

import app.models.planning  # noqa: F401
import app.models.project  # noqa: F401
from app.core.events.registry import InboundMessageEvent
from app.domain.tasks.service import (
    EventSpecError,
    TaskQueueError,
    TaskQueueService,
)
from app.models.codebase import Repository
from app.models.project import ProjectTask
from app.utils.time import utcnow


async def _mk_task(**over):
    from app.domain.tasks.service import TaskQueueService

    # Map common test aliases to actual parameter names
    if "desc" in over:
        over["description"] = over.pop("desc")
    over.setdefault("project_id", 1)
    t = await TaskQueueService.create_task(
        title=over.pop("title", "t"), **over
    )
    return t  # Return full task object, not just id


async def _get_task(tid):
    from app.domain.tasks.service import TaskQueueService

    return await TaskQueueService.get_task(tid)


class TestStatusMachine:
    async def test_user_task_starts_pending(self, _db):
        from app.domain.tasks.service import TaskQueueService

        t = await TaskQueueService.create_task(project_id=1, title="a")
        assert t.status == "pending"

    async def test_agent_task_starts_proposed(self, _db):
        from app.domain.tasks.service import TaskQueueService

        t = await TaskQueueService.create_task(project_id=1,
            title="a", source="agent"
        )
        assert t.status == "proposed"

    async def test_illegal_transition_rejected(self, _db):
        from app.domain.tasks.service import TaskQueueError, TaskQueueService

        tid = (await _mk_task()).id
        with pytest.raises(TaskQueueError) as exc:
            await TaskQueueService.advance_task(tid, "completed", result="done")
        # 错误信息必须可行动：带当前状态的合法目标（Agent 读到即能自纠）
        assert "合法目标" in str(exc.value)
        assert "in_progress" in str(exc.value)

    async def test_in_progress_to_waiting_acceptance_with_self_check_pipelines(self, _db):
        """in_progress + waiting_acceptance + self_check → 视作 self_checked 上报。

        2026-09-25 SDK 内核实测：Agent 习惯一次性携带完整自检直接申请验收，
        被状态机拒后弃收口直接文本收尾 → 回队空烧周期。self_checked 是瞬态，
        允许合并调用，终态由风险档逻辑裁决。
        """
        from app.domain.tasks.service import TaskQueueService

        # T3 无 origin（面板/工作流任务）→ 机器裁决 completed
        tid = (await _mk_task(risk_level="T3")).id
        await TaskQueueService.take_task(tid, "th-1")
        t = await TaskQueueService.advance_task(
            tid,
            "waiting_acceptance",
            result="done",
            self_check={"verdict": "pass", "checks": [{"name": "a", "pass": True}]},
        )
        assert t.status == "completed"

        # T3 带 origin（原对话评审流）→ 机器裁决 waiting_acceptance + review
        tid2 = (await _mk_task(
            risk_level="T3", source="agent", source_ref={"ref": "cli-x"}
        )).id
        await TaskQueueService.advance_task(tid2, "pending", by="user")
        await TaskQueueService.take_task(tid2, "th-2")
        t2 = await TaskQueueService.advance_task(
            tid2,
            "waiting_acceptance",
            result="done",
            self_check={"verdict": "pass", "checks": [{"name": "a", "pass": True}]},
        )
        assert t2.status == "waiting_acceptance"

    async def test_in_progress_to_waiting_acceptance_without_self_check_stays_illegal(self, _db):
        """无 self_check 的直接跳验收仍非法（错误信息带合法目标）。"""
        from app.domain.tasks.service import TaskQueueError, TaskQueueService

        tid = (await _mk_task(risk_level="T3")).id
        await TaskQueueService.take_task(tid, "th-1")
        with pytest.raises(TaskQueueError) as exc:
            await TaskQueueService.advance_task(
                tid, "waiting_acceptance", result="done"
            )
        assert "self_checked" in str(exc.value)

    async def test_t3_auto_completes_on_self_check(self, _db):
        from app.domain.tasks.service import TaskQueueService

        tid = (await _mk_task(risk_level="T3")).id
        await TaskQueueService.take_task(tid, "th-1")
        t = await TaskQueueService.advance_task(
            tid, "self_checked", result="done", self_check={"verdict": "pass"}
        )
        assert t.status == "completed"
        assert t.acceptance["by"] == "system:auto"
        assert t.acceptance["risk"] == "T3"

    async def test_missing_risk_fails_closed_to_acceptance(self, _db):
        """无 risk 等级不再默认 T3 自动完成——fail closed 等人验收。"""
        from app.domain.tasks.service import TaskQueueService

        tid = (await _mk_task()).id  # no risk_level
        await TaskQueueService.take_task(tid, "th-1")
        t = await TaskQueueService.advance_task(
            tid, "self_checked", result="done", self_check={"verdict": "pass"}
        )
        assert t.status == "waiting_acceptance"

    async def test_rejected_rework_loop(self, _db, duty_enabled):
        from app.domain.tasks.service import TaskQueueService

        tid = (await _mk_task(risk_level="T2")).id  # human acceptance required
        await TaskQueueService.take_task(tid, "th-1")
        t = await TaskQueueService.advance_task(tid, "self_checked", result="done")
        assert t.status == "waiting_acceptance"
        t = await TaskQueueService.submit_acceptance(
            tid, by="user", verdict="rejected", feedback="wrong price"
        )
        # 返工回队（而非滞留 in_progress 死局）：feedback 随任务回流给 Agent
        assert t.status == "pending"
        assert t.acceptance["feedback"] == "wrong price"
        due = await TaskQueueService.claim_due_tasks()
        assert any(x.id == tid for x in due)
        # 复跑后再次提交并验收通过
        await TaskQueueService.take_task(tid, "th-2")
        await TaskQueueService.advance_task(
            tid, "self_checked", result="fixed and resubmitted"
        )
        t = await TaskQueueService.submit_acceptance(tid, by="user", verdict="accepted")
        assert t.status == "completed"

    async def test_recurring_requeues_on_self_check(self, _db, duty_enabled):
        """Patrol task: self-check requeues (pending) instead of completing."""
        from app.domain.tasks.service import TaskQueueService

        t = await TaskQueueService.create_task(project_id=1,
            title="patrol", trigger_spec="interval:3600", risk_level="T4"
        )
        await TaskQueueService.take_task(t.id, "th-1")
        updated = await TaskQueueService.advance_task(
            t.id, "self_checked", result="no anomalies this round"
        )
        assert updated.status == "pending"  # requeued, NOT completed
        assert updated.last_result == (
            "no anomalies this round"
        )
        # next trigger 未到（next_run_at 仍在未来）→ 不立即认领：
        # recurring 的轮次间隔由 trigger 门控，而非"完成即重跑"。
        due = await TaskQueueService.claim_due_tasks()
        assert not any(x.id == t.id for x in due)
        # 到点后恢复可认领
        from app.infrastructure.database.sql.database import session_scope

        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == t.id)
                .values(next_run_at=utcnow() - timedelta(minutes=5))
            )
        due2 = await TaskQueueService.claim_due_tasks()
        assert any(x.id == t.id for x in due2)

    async def test_agent_cannot_confirm_own_proposal(self, _db):
        import json as _json

        from app.domain.tasks.service import TaskQueueService
        from app.domain.tasks.tools import tasks

        t = await TaskQueueService.create_task(project_id=1,
            title="p", source="agent"
        )
        assert t.status == "proposed"
        out = await tasks(
            action="update_status",
            task_id=t.id,
            status="pending",
            config={"configurable": {"thread_id": "th-1"}},
        )
        data = _json.loads(out)
        assert "error" in data and "user" in data["error"]
        fresh = await TaskQueueService.get_task(t.id)
        assert fresh.status == "proposed"

    async def test_agent_cannot_accept_own_work(self, _db):
        import json as _json

        from app.domain.tasks.service import TaskQueueService
        from app.domain.tasks.tools import tasks

        tid = (await _mk_task(risk_level="T2")).id
        await TaskQueueService.take_task(tid, "th-1")
        await TaskQueueService.advance_task(tid, "self_checked")
        out = await tasks(
            action="submit_acceptance",
            task_id=tid,
            config={"configurable": {"thread_id": "th-1"}},
        )
        data = _json.loads(out)
        assert "error" in data and "user API" in data["error"]
        fresh = await TaskQueueService.get_task(tid)
        assert fresh.status == "waiting_acceptance"


class TestTake:
    async def test_take_is_cas(self, _db):
        from app.domain.tasks.service import TaskQueueError, TaskQueueService

        tid = (await _mk_task()).id
        t = await TaskQueueService.take_task(tid, "th-1")
        assert t.status == "in_progress"
        assert t.last_thread_id == "th-1"
        with pytest.raises(TaskQueueError):
            await TaskQueueService.take_task(tid, "th-2")


class TestCreate:
    async def test_external_dedup(self, _db):
        from app.domain.tasks.service import TaskQueueService

        a = await TaskQueueService.create_task(project_id=1,
            title="order", source="external", dedup_key="order.paid:e1"
        )
        b = await TaskQueueService.create_task(project_id=1,
            title="order", source="external", dedup_key="order.paid:e1"
        )
        assert a.id == b.id


class TestClaim:
    async def test_due_flat_list(self, _db, duty_enabled):
        from app.domain.tasks.service import TaskQueueService

        past = utcnow() - timedelta(minutes=5)
        await TaskQueueService.create_task(project_id=1, title="o1", due_at=past)
        await TaskQueueService.create_task(project_id=1, title="o2", due_at=past)
        await TaskQueueService.create_task(project_id=2, title="g1", due_at=past)
        await TaskQueueService.create_task(project_id=1, title="future", due_at=utcnow() + timedelta(hours=1))
        due = await TaskQueueService.claim_due_tasks()
        assert {t.title for t in due} == {"o1", "o2", "g1"}

    async def test_due_ordered_by_priority_then_due(self, _db, duty_enabled):
        from app.domain.tasks.service import TaskQueueService

        past = utcnow() - timedelta(minutes=5)
        older = utcnow() - timedelta(minutes=10)
        await TaskQueueService.create_task(project_id=1, title="low", priority="low", due_at=past)
        await TaskQueueService.create_task(project_id=1, title="urgent-old", priority="urgent", due_at=older)
        await TaskQueueService.create_task(project_id=1, title="urgent-new", priority="urgent", due_at=past)
        await TaskQueueService.create_task(project_id=1, title="medium", priority="medium", due_at=past)
        due = await TaskQueueService.claim_due_tasks()
        assert [t.title for t in due] == [
            "urgent-old",
            "urgent-new",
            "medium",
            "low",
        ]

    async def test_recurring_advanced_on_claim(self, _db, duty_enabled):
        from app.domain.tasks.service import TaskQueueService

        past = utcnow() - timedelta(minutes=5)
        t = await TaskQueueService.create_task(project_id=1,
            title="patrol", trigger_spec="interval:3600"
        )
        from app.infrastructure.database.sql.database import session_scope

        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == t.id)
                .values(next_run_at=past)
            )
        due = await TaskQueueService.claim_due_tasks()
        assert any(x.id == t.id for x in due)
        # next_run_at 只在真正被 claim_for_dispatch 认领时才推进
        claimed = await TaskQueueService.claim_for_dispatch(t.id, "thread-test")
        assert claimed is not None
        fresh = await TaskQueueService.get_task(t.id)
        assert fresh.status == "in_progress"
        assert fresh.next_run_at.replace(tzinfo=None) > past.replace(tzinfo=None)

    async def test_list_filters_category_in_sql(self, _db):
        """category 筛选走 SQL 列过滤（不再内存过滤）。"""
        from app.domain.tasks.service import TaskQueueService

        await TaskQueueService.create_task(project_id=1, title="o", category="orders")
        await TaskQueueService.create_task(project_id=1, title="r", category="refunds")
        await TaskQueueService.create_task(project_id=1, title="n")  # 无 category

        orders = await TaskQueueService.list_tasks(project_id=1, category="orders")
        assert [t.title for t in orders] == ["o"]
        assert all(t.category == "orders" for t in orders)

    async def test_advance_version_conflict_detected(self, _db):
        """乐观锁：并发 advance 只有一个生效，另一个 version conflict。"""
        from app.domain.tasks.service import TaskQueueError, TaskQueueService

        tid = (await _mk_task(risk_level="T2")).id
        await TaskQueueService.take_task(tid, "th-1")

        async def _advance():
            return await TaskQueueService.advance_task(
                tid, "self_checked", result="done"
            )

        results = await asyncio.gather(_advance(), _advance(), return_exceptions=True)
        errors = [r for r in results if isinstance(r, TaskQueueError)]
        assert len(errors) == 1
        assert "version conflict" in str(errors[0])

    async def test_advance_rejects_foreign_thread(self, _db):
        """执行权归属：任务绑定 th-1 后，th-2 的 run 不能推进它。"""
        from app.domain.tasks.service import TaskQueueError, TaskQueueService

        tid = (await _mk_task(risk_level="T2")).id
        await TaskQueueService.take_task(tid, "th-1")
        with pytest.raises(TaskQueueError, match="bound to thread"):
            await TaskQueueService.advance_task(
                tid, "self_checked", result="done", thread_id="th-2"
            )
        # 绑定线程自身仍可推进
        t = await TaskQueueService.advance_task(
            tid, "self_checked", result="done", thread_id="th-1"
        )
        assert t.status == "waiting_acceptance"




    async def test_workspace_task_bypasses_project_gate(self, _db, duty_enabled):
        """pid=0（工作空间）任务不受项目分闸约束——即使没有任何项目配置值守。

        （事故回归：pid=0 曾被分闸误卡，工作空间任务永远挂起）
        """
        from datetime import timedelta

        from app.domain.tasks.service import TaskQueueService
        from app.utils.time import utcnow

        # 不写任何 project.json / duty 配置（workspace 无值守参与）
        t = await TaskQueueService.create_task(
            project_id=0,
            title="工作空间任务",
            source="user",
            due_at=utcnow() - timedelta(minutes=1),
        )
        due = await TaskQueueService.claim_due_tasks()
        assert any(x.id == t.id for x in due)


class TestTaskRuns:
    """任务与运行分离（task_runs 过程记录层）：claim 开行、终态收行。"""

    async def test_claim_opens_run_and_advance_closes_succeeded(self, _db):
        from app.domain.tasks.service import TaskQueueService

        t = await _mk_task(risk_level="T3")
        claimed = await TaskQueueService.claim_for_dispatch(t.id, "wakeup_1_run1")
        assert claimed is not None

        runs = await TaskQueueService.list_task_runs(t.id)
        assert len(runs) == 1
        assert runs[0].status == "running"
        assert runs[0].thread_id == "wakeup_1_run1"
        assert runs[0].attempt == 1

        await TaskQueueService.take_task(t.id, "wakeup_1_run1")
        await TaskQueueService.advance_task(
            t.id, "self_checked", result="done", thread_id="wakeup_1_run1"
        )
        runs = await TaskQueueService.list_task_runs(t.id)
        assert runs[0].status == "succeeded"
        assert runs[0].result_summary == "done"
        assert runs[0].finished_at is not None

    async def test_requeue_closes_run_failed(self, _db):
        from app.domain.tasks.service import TaskQueueService

        t = await _mk_task()
        await TaskQueueService.take_task(t.id, "wakeup_1_dead")
        await TaskQueueService.requeue_stuck_task(t.id, "run lost")
        runs = await TaskQueueService.list_task_runs(t.id)
        # take_task 直接绑定（无 claim_for_dispatch）→ 无 run 行，关闭幂等
        assert runs == []

    async def test_run_history_across_attempts(self, _db):
        """多次派发 → attempt 历史按序累积（不再被'最后运行'单行覆盖）。"""
        from app.domain.tasks.service import TaskQueueService

        t = await _mk_task()
        # 第一次派发失败回滚 → run(failed, dispatch_failed)
        await TaskQueueService.claim_for_dispatch(t.id, "wakeup_1_a")
        await TaskQueueService.release_dispatch_claim(t.id, "wakeup_1_a")
        # 第二次派发成功 → run(succeeded)
        await TaskQueueService.claim_for_dispatch(t.id, "wakeup_1_b")
        await TaskQueueService.advance_task(
            t.id,
            "failed",
            result="bad output",
            thread_id="wakeup_1_b",
            by="system",
        )
        runs = await TaskQueueService.list_task_runs(t.id)
        assert len(runs) == 2
        by_thread = {r.thread_id: r for r in runs}
        assert by_thread["wakeup_1_a"].status == "failed"
        assert by_thread["wakeup_1_a"].error_code == "dispatch_failed"
        assert by_thread["wakeup_1_b"].status == "failed"

    async def test_task_no_unique_constraint_enforced(self, _db):
        """(project_id, task_no) 唯一索引存在性回归（F-09 安全网）。"""
        from sqlalchemy.exc import IntegrityError

        from app.infrastructure.database.sql.database import session_scope
        from app.utils.id import gen_uuid

        with pytest.raises(IntegrityError):
            async with session_scope() as session:
                session.add_all(
                    [
                        ProjectTask(
                            id=gen_uuid(),
                            project_id=777,
                            member_id=0,
                            status="pending",
                            progress=0,
                            task_data={},
                            task_no=1,
                        ),
                        ProjectTask(
                            id=gen_uuid(),
                            project_id=777,
                            member_id=0,
                            status="pending",
                            progress=0,
                            task_data={},
                            task_no=1,
                        ),
                    ]
                )
                await session.flush()


class TestFacade:
    async def test_completed_from_in_progress_redirects_to_self_check(self, _db):
        from app.domain.tasks.service import TaskQueueService
        from app.domain.tasks.tools import tasks

        tid = (await _mk_task()).id
        await TaskQueueService.take_task(tid, "th-1")
        out = await tasks(
            action="update_status",
            task_id=tid,
            status="completed",
            result="",
            config={"configurable": {"thread_id": "th-1"}},
        )
        data = _json.loads(out)
        assert data.get("success") is True
        task = await _get_task(tid)
        assert task.status in ("waiting_acceptance", "completed")

    async def test_completed_requires_result_from_waiting_acceptance(self, _db):
        from app.domain.tasks.service import TaskQueueService
        from app.domain.tasks.tools import tasks

        tid = (await _mk_task()).id
        await TaskQueueService.take_task(tid, "th-1")
        await TaskQueueService.advance_task(tid, "self_checked", result="done")
        out = await tasks(
            action="update_status",
            task_id=tid,
            status="completed",
            result="",
            config={"configurable": {"thread_id": "th-1"}},
        )
        data = _json.loads(out)
        assert "error" in data and "result" in data["error"]

    async def test_list_surfaces_rejection_feedback(self, _db):
        from app.domain.tasks.service import TaskQueueService
        from app.domain.tasks.tools import tasks

        tid = (await _mk_task(risk_level="T2")).id
        await TaskQueueService.take_task(tid, "th-1")
        await TaskQueueService.advance_task(tid, "self_checked", result="done")
        await TaskQueueService.submit_acceptance(
            tid, by="user", verdict="rejected", feedback="wrong price"
        )
        out = await tasks(action="list", config={"configurable": {"thread_id": "t"}})
        item = next(i for i in _json.loads(out)["items"] if i["id"] == tid)
        assert item["feedback"] == "wrong price"

    async def test_list_shape(self, _db):
        from app.domain.tasks.tools import tasks

        await _mk_task(title="visible")
        out = await tasks(action="list", config={"configurable": {"thread_id": "t"}})
        data = _json.loads(out)
        assert data["count"] >= 1
        assert {"id", "title", "status"} <= set(data["items"][0].keys())


class TestReconcile:
    """DutySupervisor.reconcile_stranded — 死亡现场收敛。"""

    async def _mk_in_progress_with_activity(self, thread: str, status: str):
        from datetime import timedelta

        from app.domain.tasks.service import TaskQueueService
        from app.infrastructure.database.sql.database import session_scope
        from app.models import AgentActivity

        tid = (await _mk_task()).id
        await TaskQueueService.take_task(tid, thread)
        async with session_scope() as session:
            session.add(
                AgentActivity(
                    thread_id=thread,
                    status=status,
                    updated_at=utcnow() - timedelta(minutes=5),
                )
            )
            await session.flush()
        return tid

    async def test_terminal_run_requeues_task(self, _db, duty_enabled, monkeypatch):
        from app.domain.tasks.runtime import reconciler

        async def _fake_end_run(_thread_id, _status, **_kw):  # 不触达事件总线
            return None

        monkeypatch.setattr(reconciler, "_supervisor_end_run", _fake_end_run)
        tid = await self._mk_in_progress_with_activity("wakeup_1_a", "done")
        handled = await reconciler.reconcile_stranded(startup=True)
        assert handled == 1
        t = await _get_task(tid)
        assert t.status == "pending"
        assert (t.task_data or {}).get("requeue_count") == 1
        assert "run done" in (t.last_result or "")

    async def test_workflow_agent_thread_requeued(self, _db, duty_enabled, monkeypatch):
        """workflow 的 agent_* 线程终态 → 任务同样回队（审计 F-05 回归）。

        进程崩溃后 agent_ activity 悬挂 running、workflow 任务永久
        in_progress——reconciler 此前只认 wakeup_ 前缀。
        """
        from app.domain.tasks.runtime import reconciler

        async def _fake_end_run(_thread_id, _status, **_kw):
            return None

        monkeypatch.setattr(reconciler, "_supervisor_end_run", _fake_end_run)
        tid = await self._mk_in_progress_with_activity("agent_1_stage2", "failed")
        handled = await reconciler.reconcile_stranded(startup=True)
        assert handled == 1
        t = await _get_task(tid)
        assert t.status == "pending"

    async def test_stale_stopping_zombie_requeued(self, _db, duty_enabled, monkeypatch):
        """stopping 僵尸（进程在协作取消收尾前死亡）→ 判死 + 任务回队。

        事故回归：stopping 既非 running（判死不匹配）也非终态（回队跳过），
        任务曾永久悬挂在 in_progress。
        """
        from app.domain.tasks.runtime import reconciler

        async def _fake_end_run(_thread_id, status, **_kw):
            # 模拟 activity_monitor.end_run 的落库语义（判死 → 终态）
            from sqlalchemy import update as sa_update

            from app.infrastructure.database.sql.database import session_scope
            from app.models import AgentActivity

            async with session_scope() as session:
                await session.execute(
                    sa_update(AgentActivity)
                    .where(AgentActivity.thread_id == _thread_id)
                    .values(status=status.value)
                )

        monkeypatch.setattr(reconciler, "_supervisor_end_run", _fake_end_run)
        tid = await self._mk_in_progress_with_activity("wakeup_1_z", "stopping")
        handled = await reconciler.reconcile_stranded(startup=True)
        assert handled == 1
        t = await _get_task(tid)
        assert t.status == "pending"
        # 判死为 FAILED 后走标准回队语义
        assert "run failed" in (t.last_result or "")

    async def test_requeue_limit_fails_poison_task(self, _db, duty_enabled, monkeypatch):
        from app.domain.tasks.runtime import reconciler
        from app.domain.tasks.service import TaskQueueService

        async def _fake_end_run(_thread_id, _status, **_kw):
            return None

        monkeypatch.setattr(reconciler, "_supervisor_end_run", _fake_end_run)
        tid = (await _mk_task()).id
        await TaskQueueService.take_task(tid, "wakeup_1_b")
        # 预置 requeue_count 已达上限
        from sqlalchemy import update

        from app.infrastructure.database.sql.database import session_scope

        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == tid)
                .values(task_data={"requeue_count": 3})
            )
        from app.models import AgentActivity

        async with session_scope() as session:
            session.add(
                AgentActivity(
                    thread_id="wakeup_1_b",
                    status="done",
                    updated_at=utcnow(),
                )
            )
            await session.flush()
        await reconciler.reconcile_stranded(startup=True)
        t = await TaskQueueService.get_task(tid)
        assert t.status == "failed"

    async def test_orphan_suspended_run_requeued(self, _db):
        """human_interrupt WITHOUT a pending request is an orphan — requeued."""
        from app.domain.tasks.runtime import reconciler

        tid = await self._mk_in_progress_with_activity(
            "wakeup_1_c", "human_interrupt"
        )
        handled = await reconciler.reconcile_stranded(startup=True)
        assert handled == 1
        t = await _get_task(tid)
        assert t.status == "pending"

    async def test_suspended_run_with_pending_hitl_not_requeued(self, _db):
        """human_interrupt WITH a pending request → exempt (operator away)."""
        from app.domain.tasks.runtime import reconciler
        from app.models import HumanRequest

        tid = await self._mk_in_progress_with_activity(
            "wakeup_1_d", "human_interrupt"
        )
        from app.infrastructure.database import session_scope as _ss

        async with _ss() as session:
            session.add(
                HumanRequest(
                    id="hr-1",
                    thread_id="wakeup_1_d",
                    type="approval",
                    description="wait",
                    status="pending",
                )
            )
        handled = await reconciler.reconcile_stranded(startup=True)
        assert handled == 0
        t = await _get_task(tid)
        assert t.status == "in_progress"

    async def test_no_activity_fresh_claim_within_grace_not_requeued(self, _db, duty_enabled):
        """刚认领（无 activity 记录）的任务在宽限期内不得被 reconciler 秒杀。

        认领（in_progress+绑线程）→ run 启动（activity 落库）之间存在秒级
        窗口：此前 reconciler 扫过窗口即判 "run lost" 回队，造成反复重派
        →熔断误杀（2026-09-24 实测事故链）。
        """
        from app.domain.tasks.runtime import reconciler
        from app.domain.tasks.service import TaskQueueService

        tid = (await _mk_task()).id
        await TaskQueueService.take_task(tid, "wakeup_1_fresh")

        # 稳态 reconcile（updated_at=现在，处于 NO_ACTIVITY_GRACE_SECONDS 内）
        handled = await reconciler.reconcile_stranded()
        assert handled == 0
        t = await _get_task(tid)
        assert t.status == "in_progress"

        # 宽限期过后仍无 activity → 正常判死回队
        from sqlalchemy import update as sa_update

        from app.infrastructure.database.sql.database import session_scope

        async with session_scope() as session:
            await session.execute(
                sa_update(ProjectTask)
                .where(ProjectTask.id == tid)
                .values(updated_at=utcnow() - timedelta(minutes=5))
            )
        handled = await reconciler.reconcile_stranded()
        assert handled == 1
        t = await _get_task(tid)
        assert t.status == "pending"
        assert "run lost" in (t.last_result or "")

    async def test_review_pending_naive_updated_at_no_crash(self, _db, duty_enabled, monkeypatch):
        """review_pending + naive updated_at：不得 TypeError 炸掉整个 reconcile。

        sqlite 驱动返回 naive datetime，直接与 aware now 相减曾让
        reconcile_stranded 每轮中断——HITL 过期/判死/回队全部失效。
        """
        from app.domain.tasks.runtime import reconciler

        tid = (await _mk_task()).id
        from sqlalchemy import update as sa_update

        from app.infrastructure.database.sql.database import session_scope

        async with session_scope() as session:
            await session.execute(
                sa_update(ProjectTask)
                .where(ProjectTask.id == tid)
                .values(
                    status="waiting_acceptance",
                    origin_thread_id="chat-thread-review",
                    review_pending=True,
                    updated_at=utcnow() - timedelta(minutes=40),
                )
            )

        calls: list[str] = []

        async def _fake_resolve(task_id: str, _conclusion: str) -> None:
            calls.append(task_id)

        monkeypatch.setattr(
            "app.domain.tasks.review.resolve_review_verdict", _fake_resolve
        )
        handled = await reconciler.reconcile_stranded()
        assert calls == [tid]
        assert handled >= 1

    async def test_pending_hitl_thread_exempt(self, _db):

        from app.domain.tasks.runtime import reconciler
        from app.infrastructure.database.sql.database import session_scope
        from app.models import HumanRequest

        tid = await self._mk_in_progress_with_activity("wakeup_1_d", "done")
        async with session_scope() as session:
            session.add(
                HumanRequest(
                    id="hr-1",
                    thread_id="wakeup_1_d",
                    type="choice",
                    description="stop or continue?",
                    status="pending",
                )
            )
            await session.flush()
        handled = await reconciler.reconcile_stranded(startup=True)
        assert handled == 0
        t = await _get_task(tid)
        assert t.status == "in_progress"

    async def test_stale_running_reaped_then_requeued(self, _db, duty_enabled, monkeypatch):
        from app.domain.tasks.runtime import reconciler

        ended: list[tuple[str, str]] = []

        async def _fake_end_run(thread_id, status, **_kw):
            ended.append((thread_id, status))
            # 模拟真实 end_run 的落库效果（状态推进到终态）
            from sqlalchemy import update

            from app.infrastructure.database.sql.database import session_scope
            from app.models import AgentActivity

            async with session_scope() as session:
                await session.execute(
                    update(AgentActivity)
                    .where(AgentActivity.thread_id == thread_id)
                    .values(status=status.value)
                )

        monkeypatch.setattr(reconciler, "_supervisor_end_run", _fake_end_run)
        tid = await self._mk_in_progress_with_activity("wakeup_1_e", "running")
        handled = await reconciler.reconcile_stranded(startup=True)
        from app.core.monitoring.constants import ActivityStatus

        assert ("wakeup_1_e", ActivityStatus.FAILED) in ended
        assert handled == 1
        t = await _get_task(tid)
        assert t.status == "pending"

    async def test_user_threads_never_touched(self, _db):
        from app.domain.tasks.runtime import reconciler
        from app.domain.tasks.service import TaskQueueService

        tid = (await _mk_task()).id
        await TaskQueueService.take_task(tid, "user-thread-not-duty")
        handled = await reconciler.reconcile_stranded(startup=True)
        assert handled == 0
        t = await _get_task(tid)
        assert t.status == "in_progress"


class TestClaimDutySwitch:
    async def test_disabled_project_skipped(self, _db, monkeypatch):
        from app.domain.tasks.service import TaskQueueService

        async def _fake_cfg(project_id):
            if project_id == 1:
                return {"enabled": False}
            return {"enabled": True}

        monkeypatch.setattr(
            "app.core.channel.duty.config.load_duty_config", _fake_cfg
        )
        past = utcnow() - timedelta(minutes=5)
        await TaskQueueService.create_task(project_id=1, title="off", due_at=past)
        await TaskQueueService.create_task(project_id=2, title="on", due_at=past)
        due = await TaskQueueService.claim_due_tasks()
        assert [t.project_id for t in due] == [2]

    async def test_unconfigured_project_opt_in_gated(self, _db, monkeypatch):
        """缺省关闭：未启用值守的项目任务挂起（opt-in 语义）。"""
        from app.domain.tasks.service import TaskQueueService

        async def _fake_cfg(_project_id):
            return {}

        monkeypatch.setattr(
            "app.core.channel.duty.config.load_duty_config", _fake_cfg
        )
        past = utcnow() - timedelta(minutes=5)
        await TaskQueueService.create_task(project_id=7, title="legacy", due_at=past)
        due = await TaskQueueService.claim_due_tasks()
        assert due == []


class TestWakeupSubscriber:
    async def test_wakeup_thread_notifies(self, _db):
        from types import SimpleNamespace

        from app.domain.tasks.event.subscribers import duty_wakeup_subscriber
        from app.domain.tasks.runtime.wakeup import _event

        _event().clear()
        sub = duty_wakeup_subscriber
        await sub.on_agent_run_completed(SimpleNamespace(thread_id="wakeup_1_x"))
        assert _event().is_set()

    async def test_non_duty_thread_ignored(self, _db):
        from types import SimpleNamespace

        from app.domain.tasks.event.subscribers import duty_wakeup_subscriber
        from app.domain.tasks.runtime.wakeup import _event

        _event().clear()
        sub = duty_wakeup_subscriber
        await sub.on_agent_run_completed(SimpleNamespace(thread_id="chat-abc"))
        assert not _event().is_set()


class TestDispatcher:
    """dispatch_due_tasks 编排验证——全程 stub 引擎，不需要 LLM。"""

    def _patch_engine(self, monkeypatch, captured: dict, tmp_path):
        from types import SimpleNamespace

        from app.core.engine.dispatch import DispatchStatus

        async def _fake_dispatch(**kwargs):
            captured.setdefault("dispatches", []).append(kwargs)
            return SimpleNamespace(
                status=DispatchStatus.QUEUED, inputs={"messages": []}, error=None
            )

        async def _fake_run(thread_id, _inputs):
            captured.setdefault("ran", []).append(thread_id)
            # 模拟 Agent take：任务进入 in_progress，不再可认领（真实语义：
            # run 未 take 的任务会被下一轮 drain 重派，这是连续运行的预期行为）
            from app.domain.tasks.service import TaskQueueService

            task_id = captured["dispatches"][-1]["metadata"]["source_task_id"]
            await TaskQueueService.take_task(task_id, thread_id)

        monkeypatch.setattr(
            "app.core.engine.dispatch.dispatch_agent_run", _fake_dispatch
        )
        monkeypatch.setattr(
            "app.core.engine.agent.run_agent_background", _fake_run
        )
        monkeypatch.setattr(
            "app.core.engine.capability_profiles.list_domains", lambda _: []
        )
        import json as _json

        proj_dir = tmp_path / "project-1"
        (proj_dir / ".evoloop").mkdir(parents=True)
        (proj_dir / ".evoloop" / "project.json").write_text(
            _json.dumps({"customer_service_duty": {"enabled": True}})
        )

        async def _fake_gpp(*_a, **_k):
            return str(proj_dir)

        monkeypatch.setattr(
            "app.core.project.utils.get_project_path", _fake_gpp
        )
        # config.py 顶层 import 持有独立绑定，必须一并 patch
        monkeypatch.setattr(
            "app.core.channel.duty.config.get_project_path", _fake_gpp
        )

    async def test_dispatch_orchestration(self, _db, monkeypatch, tmp_path):
        from datetime import timedelta

        from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks
        from app.infrastructure.database.sql.database import session_scope

        captured: dict = {}
        self._patch_engine(monkeypatch, captured, tmp_path)

        tid = (
            await _mk_task(
                title="patrol-x", desc="巡检指令原文", due_at=utcnow() - timedelta(minutes=1)
            )
        ).id
        async with session_scope() as session:
            session.add(Repository(id=1, project_id=1, name="p1", url="https://x", member_id=5))
            await session.flush()

        await dispatch_due_tasks()

        d = captured["dispatches"][0]
        assert d["member_id"] == 5  # task.member_id=0 → repositories 回填
        assert d["metadata"]["source"] == "duty"
        assert d["metadata"]["source_task_id"] == tid
        assert d["thread_id"].startswith("wakeup_1_")
        # 任务描述即第一条 human 消息全文（不经模板包装）；title 走系统块
        assert d["message_content"] == "巡检指令原文"
        assert d["metadata"]["duty_task"]["title"] == "patrol-x"
        assert d["metadata"]["duty_task"]["id"] == tid
        assert captured["ran"] == [d["thread_id"]]  # run 真被启动（stub，无 LLM）

        # 队列已空：再次 drain 立即返回，不重复派发
        await dispatch_due_tasks()
        assert len(captured["dispatches"]) == 1

    async def test_rejected_feedback_in_payload(self, _db, monkeypatch, tmp_path):

        from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks
        from app.domain.tasks.service import TaskQueueService

        captured: dict = {}
        self._patch_engine(monkeypatch, captured, tmp_path)

        tid = (await _mk_task(risk_level="T2")).id
        await TaskQueueService.take_task(tid, "wakeup_1_f")
        await TaskQueueService.advance_task(tid, "self_checked", result="done")
        await TaskQueueService.submit_acceptance(
            tid, by="user", verdict="rejected", feedback="金额算错了"
        )

        await dispatch_due_tasks()

        d = captured["dispatches"][0]
        # 评审反馈走系统块 metadata.duty_task（不再包装进 human 消息）
        content = d["message_content"]
        assert "金额算错了" not in content
        assert "REJECTED" not in content
        assert d["metadata"]["duty_task"]["feedback"] == "金额算错了"

    async def test_watchdog_hard_cancel(self, _db, monkeypatch, tmp_path):
        import asyncio

        from app.domain.tasks.runtime import dispatcher

        monkeypatch.setattr(dispatcher, "WAKEUP_RUN_DEADLINE_SECONDS", 0.05)

        async def _fake_dispatch(**kwargs):  # noqa: ARG001 — 哨兵签名
            from types import SimpleNamespace

            from app.core.engine.dispatch import DispatchStatus

            return SimpleNamespace(
                status=DispatchStatus.QUEUED, inputs={"messages": []}, error=None
            )

        cancelled = {"n": 0}

        async def _fake_slow_run(_thread_id, _inputs):
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                cancelled["n"] += 1
                raise

        monkeypatch.setattr(
            "app.core.engine.dispatch.dispatch_agent_run", _fake_dispatch
        )
        monkeypatch.setattr(
            "app.core.engine.agent.run_agent_background", _fake_slow_run
        )
        monkeypatch.setattr(
            "app.core.engine.capability_profiles.list_domains", lambda _: []
        )
        import json as _json

        proj_dir = tmp_path / "project-1"
        (proj_dir / ".evoloop").mkdir(parents=True)
        (proj_dir / ".evoloop" / "project.json").write_text(
            _json.dumps({"customer_service_duty": {"enabled": True}})
        )

        async def _fake_gpp(*_a, **_k):
            return str(proj_dir)

        monkeypatch.setattr(
            "app.core.project.utils.get_project_path", _fake_gpp
        )
        # config.py 顶层 import 持有独立绑定，必须一并 patch
        monkeypatch.setattr(
            "app.core.channel.duty.config.get_project_path", _fake_gpp
        )

        from datetime import timedelta

        await _mk_task(due_at=utcnow() - timedelta(minutes=1))
        await dispatcher.dispatch_due_tasks()  # 不应抛超时异常
        assert cancelled["n"] == 1


# ── 外部事件摄取（原 test_ingestion.py，ingest_event 收编 TaskQueueService）──

ingest_event = TaskQueueService.ingest_event

MALL_SERVER = "capability-matrix-online"

SPEC = {
    "title": "Confirm shipping for order #1001",
    "category": "orders",
    "priority": "high",
    "risk_level": "T3",
    "project_id": 1,
}


class TestIngest:
    async def test_creates_external_task(self, _db):
        task, created = await ingest_event("mall", "e-1", dict(SPEC))
        assert created is True
        # external 低可信来源 fail-closed：提案确认后才入列执行
        assert task.status == "proposed"
        assert task.source == "external"
        assert task.risk_level == "T3"
        assert task.due_at is None  # dispatchable immediately once confirmed

    async def test_idempotent_on_event_id(self, _db):
        a, created_a = await ingest_event("mall", "e-1", dict(SPEC))
        b, created_b = await ingest_event("mall", "e-1", dict(SPEC))
        assert created_a is True and created_b is False
        assert a.id == b.id

    async def test_same_event_id_diff_source_not_deduped(self, _db):
        a, _ = await ingest_event("mall", "e-1", dict(SPEC))
        b, created_b = await ingest_event("crm", "e-1", dict(SPEC))
        assert created_b is True
        assert a.id != b.id

    async def test_missing_title_rejected(self, _db):
        bad = {k: v for k, v in SPEC.items() if k != "title"}
        with pytest.raises(EventSpecError):
            await ingest_event("mall", "e-2", bad)

    async def test_start_in_hours_defers_dispatch(self, _db):
        from datetime import timedelta

        from app.utils.time import utcnow

        spec = {**SPEC, "start_in_hours": 2}
        task, _ = await ingest_event("mall", "e-start", spec)
        assert task.due_at is not None
        delta = task.due_at.replace(tzinfo=utcnow().tzinfo) - utcnow()
        assert timedelta(hours=1) < delta <= timedelta(hours=2, minutes=5)


class TestInboundMessagePath:
    """InboundMessageSubscriber：channel 归一化消息 → 任务入队。"""

    def _event(self, **overrides) -> InboundMessageEvent:
        fields = {
            "source_system": MALL_SERVER,
            "event_id": "e-10",
            "project_id": 1,
            "title": SPEC["title"],
            "content": "order paid, confirm shipping",
            "category": SPEC["category"],
            "priority": SPEC["priority"],
            "risk_level": SPEC["risk_level"],
        }
        fields.update(overrides)
        return InboundMessageEvent(**fields)

    async def test_inbound_message_creates_task(self, _db):
        from app.domain.tasks.event.subscribers import inbound_message_subscriber

        sub = inbound_message_subscriber
        await sub.on_inbound_message(self._event())
        task, created = await ingest_event(MALL_SERVER, "e-10", dict(SPEC))
        assert created is False  # already created by the subscriber

    async def test_contact_persists_in_source_ref(self, _db):
        from app.domain.tasks.event.subscribers import inbound_message_subscriber

        sub = inbound_message_subscriber
        await sub.on_inbound_message(self._event(event_id="e-contact", contact="wxid_abc"))
        task, created = await ingest_event(
            MALL_SERVER,
            "e-contact",
            {**SPEC, "contact": "wxid_abc"},
        )
        assert created is False  # dedup 命中，返回已落库任务
        assert (task.source_ref or {}).get("contact") == "wxid_abc"

    async def test_channel_persists_in_source_ref(self, _db):
        from app.domain.tasks.event.subscribers import inbound_message_subscriber

        sub = inbound_message_subscriber
        await sub.on_inbound_message(
            self._event(event_id="e-ch", contact="wxid_abc", channel="mcp_message")
        )
        task, _ = await ingest_event(
            MALL_SERVER, "e-ch", {**SPEC, "contact": "wxid_abc", "channel": "mcp_message"}
        )
        source_ref = task.source_ref or {}
        assert source_ref.get("channel") == "mcp_message"
        assert source_ref.get("source_system") == MALL_SERVER


class TestSessionReplyRouter:
    """wakeup 会话终态 → 回复路由决策（contact + channel 齐备才发）。"""

    def _completed(self, thread_id: str, summary: str = "done") -> SimpleNamespace:
        return SimpleNamespace(data=SimpleNamespace(thread_id=thread_id, summary=summary))

    async def _mk_task_with_thread(self, thread_id: str, source_ref: dict) -> str:
        from sqlalchemy import update

        from app.infrastructure.database.sql.database import session_scope

        t = await TaskQueueService.create_task(
            project_id=1,
            title="t",
            source="external",
            source_ref=source_ref,
            dedup_key=f"test:{source_ref.get('event_id')}",
        )
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask)
                .where(ProjectTask.id == t.id)
                .values(last_thread_id=thread_id)
            )
        return t.id

    async def _capture_outbound(self, monkeypatch) -> list:
        from app.core.events.registry import OutboundReplyEvent

        captured: list[OutboundReplyEvent] = []

        async def _fake_publish(event):
            captured.append(event)

        monkeypatch.setattr(
            "app.domain.tasks.event.subscribers.system_bus",
            SimpleNamespace(publish=_fake_publish),
        )
        return captured

    async def test_reply_routed_on_contact_and_channel(self, _db, monkeypatch):
        from app.domain.tasks.event.subscribers import session_reply_router

        thread_id = "wakeup_1_task-1"
        await self._mk_task_with_thread(
            thread_id,
            {
                "kind": "event",
                "source_system": MALL_SERVER,
                "event_id": "e-r1",
                "contact": "wxid_abc",
                "channel": "mcp_message",
            },
        )
        captured = await self._capture_outbound(monkeypatch)
        await session_reply_router.on_session_completed(self._completed(thread_id))
        assert len(captured) == 1
        evt = captured[0]
        assert evt.channel == "mcp_message"
        assert evt.recipient == "wxid_abc"
        assert evt.content == "done"
        assert evt.source_system == MALL_SERVER
        assert evt.project_id == 1

    async def test_no_contact_no_reply(self, _db, monkeypatch):
        from app.domain.tasks.event.subscribers import session_reply_router

        thread_id = "wakeup_1_task-2"
        await self._mk_task_with_thread(
            thread_id,
            {"kind": "event", "source_system": MALL_SERVER, "event_id": "e-r2"},
        )
        captured = await self._capture_outbound(monkeypatch)
        await session_reply_router.on_session_completed(self._completed(thread_id))
        assert captured == []

    async def test_non_wakeup_thread_ignored(self, _db, monkeypatch):
        from app.domain.tasks.event.subscribers import session_reply_router

        captured = await self._capture_outbound(monkeypatch)
        await session_reply_router.on_session_completed(self._completed("duty_1_wxid_abc"))
        assert captured == []

    async def test_empty_summary_ignored(self, _db, monkeypatch):
        from app.domain.tasks.event.subscribers import session_reply_router

        captured = await self._capture_outbound(monkeypatch)
        await session_reply_router.on_session_completed(self._completed("wakeup_1_x", summary=""))
        assert captured == []

    async def test_unknown_thread_no_reply(self, _db, monkeypatch):
        from app.domain.tasks.event.subscribers import session_reply_router

        captured = await self._capture_outbound(monkeypatch)
        await session_reply_router.on_session_completed(self._completed("wakeup_9_ghost"))
        assert captured == []



class TestQuotaBreaker:
    """配额熔断：quota_exhausted → 暂停值守派发（实测暴露的策略缺口）。"""

    async def test_pause_blocks_drain_and_expires(self, _db, monkeypatch, tmp_path):
        from app.domain.tasks.runtime import dispatcher

        async def _fake_cfg(_pid):
            return {"enabled": True}

        monkeypatch.setattr(
            "app.core.channel.duty.config.load_duty_config", _fake_cfg
        )

        # 1) 熔断生效：dispatch_due_tasks 直接返回，不派发
        dispatcher.pause_duty_for(15)
        assert dispatcher.duty_paused() is True
        await dispatcher.dispatch_due_tasks()  # 不应派发任何任务

        # 2) 熔断到期：恢复派发（task 在冷却期内仍会被正常认领）
        #    直接拨快熔断时间戳
        dispatcher._quota_paused_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert dispatcher.duty_paused() is False

        # 清理：避免影响其他用例
        dispatcher._quota_paused_until = None

    async def test_quota_terminal_triggers_pause(self, _db, monkeypatch, tmp_path):
        from datetime import timedelta

        from app.core.monitoring.constants import ActivityStatus
        from app.domain.tasks.constants import QUOTA_COOLDOWN_MINUTES
        from app.domain.tasks.runtime import reconciler

        async def _fake_cfg(_pid):
            return {"enabled": True}

        monkeypatch.setattr(
            "app.core.channel.duty.config.load_duty_config", _fake_cfg
        )
        paused: list[float] = []

        def _fake_pause(minutes):
            paused.append(minutes)

        import app.domain.tasks.runtime.dispatcher as _dispatcher

        monkeypatch.setattr(_dispatcher, "pause_duty_for", _fake_pause)

        # 任务 + quota_exhausted 终态 activity
        from app.domain.tasks.service import TaskQueueService
        from app.infrastructure.database.sql.database import session_scope
        from app.models import AgentActivity

        tid = (await _mk_task()).id
        await TaskQueueService.take_task(tid, "wakeup_1_q")
        async with session_scope() as session:
            session.add(
                AgentActivity(
                    thread_id="wakeup_1_q",
                    status=ActivityStatus.QUOTA_EXHAUSTED.value,
                    updated_at=utcnow() - timedelta(minutes=5),
                )
            )
            await session.flush()

        await reconciler.reconcile_stranded(startup=True)
        assert paused == [QUOTA_COOLDOWN_MINUTES]
        # 任务照常回队（配额恢复后可重试）
        t = await _get_task(tid)
        assert t.status == "pending"


class TestQuotaResetParse:
    """429 错误文本 → 配额重置时间（熔断到重置点，而非固定冷却）。"""

    async def test_parse_reset_time(self, _db):
        from types import SimpleNamespace

        from app.domain.tasks.event.subscribers import _quota_reset_time

        event = SimpleNamespace(
            payload={"summary": '429 Too Many Requests "It will reset at '
            '2026-09-14 00:00:00 +0800 CST"'}
        )
        reset = _quota_reset_time(event)
        assert reset is not None
        assert reset.hour == 0 and reset.day == 14  # 北京时间 00:00 → UTC 前一天 16:00+1min
        assert reset.tzinfo is not None

    async def test_parse_missing_returns_none(self, _db):
        from types import SimpleNamespace

        from app.domain.tasks.event.subscribers import _quota_reset_time

        assert _quota_reset_time(SimpleNamespace(payload={})) is None
        assert _quota_reset_time(SimpleNamespace(payload={"summary": "no reset info"})) is None

    async def test_pause_until_reset_not_fixed_cooldown(self, _db, monkeypatch):
        """quota 事件 → 熔断到重置点（而非固定 15 分钟）。"""
        from datetime import timedelta
        from types import SimpleNamespace

        from app.core.monitoring.constants import ActivityStatus
        from app.domain.tasks.runtime import dispatcher
        from app.domain.tasks.runtime.wakeup import _event

        called = {}

        def _fake_until(until):
            called["until"] = until

        monkeypatch.setattr(dispatcher, "pause_duty_until", _fake_until)


        event = SimpleNamespace(
            thread_id="wakeup_1_x",
            status=ActivityStatus.QUOTA_EXHAUSTED,
            payload={"summary": "It will reset at 2026-09-14 00:00:00 +0800 CST."},
        )
        _event().clear()
        from app.domain.tasks.event.subscribers import duty_wakeup_subscriber

        sub = duty_wakeup_subscriber
        await sub.on_agent_run_completed(event)
        assert "until" in called
        # 熔断到重置点（00:00+08:00 = 16:00 UTC 13 日）+ 1min，远于固定 15min 冷却
        expected = datetime.fromisoformat("2026-09-13T16:00:00+00:00") + timedelta(minutes=1)
        assert called["until"] == expected
        assert _event().is_set()

# ============================================================
# 额外测试：补齐 coverage gap
# ============================================================

# ============================================================
# 额外测试：补齐 coverage gap
# ============================================================

class TestFacadeTool:
    """tools/tasks_tool.py 覆盖补全"""

    async def test_list_no_filter(self, _db):
        """list 无过滤返回所有任务"""
        from app.domain.tasks.tools import tasks

        # 创建两个任务
        t1 = await _mk_task(title="t1", project_id=1)
        t2 = await _mk_task(title="t2")

        out = await tasks(action="list")
        data = _json.loads(out)
        assert data["count"] >= 2
        ids = {item["id"] for item in data["items"]}
        assert {t1.id, t2.id}.issubset(ids)

    async def test_list_project_filter(self, _db, monkeypatch):
        """list 支持项目过滤"""
        from app.core.context.manager import ContextManager
        from app.domain.tasks.tools import tasks

        # 创建两个项目的任务
        await _mk_task(title="p1")
        await _mk_task(project_id=2, title="p2")

        # 设置项目上下文为 project 1
        monkeypatch.setattr(ContextManager, "current", lambda: SimpleNamespace(project_id=1))

        out = await tasks(action="list")
        data = _json.loads(out)
        assert data["count"] == 1
        assert data["items"][0]["title"] == "p1"

    async def test_create_user_source_forced_to_agent(self, _db, monkeypatch):
        """工具面创建一律 source=agent（审计 P1-03：来源不由模型自报）——
        传 source="user" 伪装人工通道绕过提案闸的口子已封死。"""
        from app.core.context.manager import ContextManager
        from app.domain.tasks.tools import tasks

        monkeypatch.setattr(ContextManager, "current", lambda: SimpleNamespace(project_id=1))

        out = await tasks(action="create", title="new task", source="user")
        data = _json.loads(out)
        assert data["success"] is True
        assert data["status"] == "proposed"

        # 验证入库：强制 agent 来源 → proposed
        task = await TaskQueueService.get_task(data["id"])
        assert task.status == "proposed"
        assert task.source == "agent"

    async def test_create_agent_source(self, _db, monkeypatch):
        """agent source 创建 proposed 任务"""
        from app.core.context.manager import ContextManager
        from app.domain.tasks.tools import tasks

        monkeypatch.setattr(
            ContextManager,
            "current",
            lambda: SimpleNamespace(current_task_id="current-task", project_id=1),
        )

        out = await tasks(action="create", title="agent task", source="agent")
        data = _json.loads(out)
        assert data["success"] is True
        assert data["status"] == "proposed"

        task = await TaskQueueService.get_task(data["id"])
        assert task.status == "proposed"
        assert task.source == "agent"
        assert task.source_ref.get("task_id") == "current-task"

    async def test_create_agent_proposal_without_origin_task(self, _db, monkeypatch):
        """聊天入口创建提案时没有正在执行的任务 ID，也能创建 proposed 任务"""
        from app.core.context.manager import ContextManager
        from app.domain.tasks.tools import tasks

        monkeypatch.setattr(
            ContextManager,
            "current",
            lambda: SimpleNamespace(project_id=1),
        )

        out = await tasks(
            action="create",
            title="chat proposal",
            description="created from chat",
            source="agent",
            config={"configurable": {"thread_id": "chat-thread"}},
        )
        data = _json.loads(out)
        assert data["success"] is True
        assert data["status"] == "proposed"

        task = await TaskQueueService.get_task(data["id"])
        assert task is not None
        assert task.status == "proposed"
        assert task.source == "agent"
        assert task.source_ref == {"kind": "message", "ref": "chat-thread"}

    async def test_take_success(self, _db, monkeypatch):
        """take 成功：pending -> in_progress + thread 绑定"""
        from app.core.context.manager import ContextManager
        from app.domain.tasks.tools import tasks

        monkeypatch.setattr(ContextManager, "current", lambda: SimpleNamespace(thread_id="thread-123", project_id=1))

        t = await _mk_task()
        out = await tasks(action="take", task_id=t.id, config={"configurable": {"thread_id": "thread-123"}})
        data = _json.loads(out)
        assert data["success"] is True
        assert data["status"] == "in_progress"

        task = await TaskQueueService.get_task(data["id"])
        assert task.status == "in_progress"
        assert task.last_thread_id == "thread-123"

    async def test_take_cross_project_reject(self, _db, monkeypatch):
        """take 跨项目拒绝"""
        from app.core.context.manager import ContextManager
        from app.domain.tasks.tools import tasks

        monkeypatch.setattr(ContextManager, "current", lambda: SimpleNamespace(project_id=1))

        t = await _mk_task(project_id=2)  # 不同项目
        out = await tasks(
            action="take", task_id=t.id,
            config={"configurable": {"thread_id": "thread-123"}},
        )
        data = _json.loads(out)
        assert "error" in data
        assert "belongs to another project" in data["error"]

    async def test_update_status_proposed_guard(self, _db):
        """update_status: proposed 状态被拒绝（仅用户可确认）"""
        from app.domain.tasks.tools import tasks

        t = await TaskQueueService.create_task(project_id=1,
            title="proposed", source="agent"
        )
        assert t.status == "proposed"

        out = await tasks(action="update_status", task_id=t.id, status="pending")
        data = _json.loads(out)
        assert "error" in data
        assert "user" in data["error"]

    async def test_update_status_completed_from_in_progress_redirects(self, _db):
        """update_status: in_progress → completed 自动重定向为 self_checked"""
        from app.domain.tasks.tools import tasks

        t = await _mk_task()
        await TaskQueueService.take_task(t.id, "th-1")

        out = await tasks(action="update_status", task_id=t.id, status="completed", result="")
        data = _json.loads(out)
        assert data.get("success") is True
        task = await _get_task(t.id)
        assert task.status in ("waiting_acceptance", "completed")

    async def test_update_status_completed_requires_result_from_waiting_acceptance(self, _db):
        """update_status: waiting_acceptance → completed 仍要求 result"""
        from app.domain.tasks.tools import tasks

        t = await _mk_task()
        await TaskQueueService.take_task(t.id, "th-1")
        await TaskQueueService.advance_task(t.id, "self_checked", result="done")

        out = await tasks(action="update_status", task_id=t.id, status="completed", result="")
        data = _json.loads(out)
        assert "error" in data
        assert "result" in data["error"]

    async def test_update_status_rejected_rework(self, _db, monkeypatch):
        """rejected 回队后可重新 take -> self_checked -> completed"""
        from app.core.context.manager import ContextManager
        from app.domain.tasks.tools import tasks

        monkeypatch.setattr(ContextManager, "current", lambda: SimpleNamespace(project_id=1))

        t = await _mk_task(risk_level="T2")
        await TaskQueueService.take_task(t.id, "th-1")
        await TaskQueueService.advance_task(t.id, "self_checked", result="done")
        await TaskQueueService.submit_acceptance(t.id, by="user", verdict="rejected", feedback="wrong")

        # rejected -> pending；重新 take 再推进到 self_checked 再完成
        assert (await TaskQueueService.get_task(t.id)).status == "pending"
        out = await tasks(
            action="take", task_id=t.id,
            config={"configurable": {"thread_id": "th-2"}},
        )
        assert _json.loads(out)["success"] is True
        # in_progress -> self_checked
        out = await tasks(action="update_status", task_id=t.id, status="self_checked", result="rework done")
        data = _json.loads(out)
        assert data["success"] is True
        assert data["status"] == "waiting_acceptance"
        # waiting_acceptance -> completed
        out = await tasks(action="update_status", task_id=t.id, status="completed", result="fixed")
        data = _json.loads(out)
        assert data["success"] is True
        assert data["status"] == "completed"

    async def test_submit_acceptance_via_tool_rejected_feedback(self, _db, monkeypatch):
        """submit_acceptance 属用户 API，agent 工具一律拒绝（feedback 错误在 user 层）"""
        from app.core.context.manager import ContextManager
        from app.domain.tasks.tools import tasks

        monkeypatch.setattr(ContextManager, "current", lambda: SimpleNamespace(project_id=1))

        t = await _mk_task(risk_level="T2")
        await TaskQueueService.take_task(t.id, "th-1")
        await TaskQueueService.advance_task(t.id, "self_checked", result="done")

        out = await tasks(action="submit_acceptance", task_id=t.id)
        data = _json.loads(out)
        assert "error" in data
        assert "user API" in data["error"]

    async def test_submit_acceptance_agent_forbidden(self, _db, monkeypatch):
        """submit_acceptance: Agent 禁止操作"""
        from app.core.context.manager import ContextManager
        from app.domain.tasks.tools import tasks

        monkeypatch.setattr(ContextManager, "current", lambda: SimpleNamespace(project_id=1))

        t = await _mk_task(risk_level="T2")
        await TaskQueueService.take_task(t.id, "th-1")
        await TaskQueueService.advance_task(t.id, "self_checked", result="done")

        out = await tasks(action="submit_acceptance", task_id=t.id)
        data = _json.loads(out)
        assert "error" in data
        assert "user API" in data["error"]

    async def test_submit_acceptance_via_tool_rejected(self, _db):
        """submit_acceptance 属用户 API，agent 工具一律拒绝"""
        from app.domain.tasks.tools import tasks

        t = await _mk_task(risk_level="T2")
        await TaskQueueService.take_task(t.id, "th-1")
        await TaskQueueService.advance_task(t.id, "self_checked", result="done")

        out = await tasks(action="submit_acceptance", task_id=t.id)
        data = _json.loads(out)
        assert "error" in data
        assert "user API" in data["error"]


class TestTaskServiceExtended:
    """TaskQueueService 核心方法完整覆盖"""

    async def test_create_task_user_source(self, _db):
        """user 源 -> pending"""
        task = await TaskQueueService.create_task(project_id=1,
            title="user task", source="user"
        )
        assert task.status == "pending"
        assert task.source == "user"

    async def test_create_task_agent_source(self, _db):
        """agent 源 -> proposed + source_ref 绑定上游任务"""
        from unittest.mock import patch

        with patch("app.core.context.manager.ContextManager.current") as mock_ctx:
            mock_ctx.return_value = SimpleNamespace(task_id="parent-123", project_id=1)

            task = await TaskQueueService.create_task(project_id=1,
                title="agent task", source="agent"
            )
            assert task.status == "proposed"
            assert task.source == "agent"
            # service 层 create_task 不解释上下文，source_ref 为空
        # origin task 绑定由 tasks 工具层写 source_ref（见 TestFacadeTool）
        assert task.source_ref == {}

    async def test_create_task_external_source(self, _db):
        """external 源 -> proposed（外部推单需确认，fail-closed）"""
        task = await TaskQueueService.create_task(project_id=1,
            title="external", source="external"
        )
        assert task.status == "proposed"
        assert task.source == "external"

    async def test_take_is_cas(self, _db):
        """take 是原子 CAS：并发抢同一任务，只有一个成功（另一个 raise）"""
        from app.domain.tasks.service import TaskQueueError, TaskQueueService

        t = await _mk_task()

        results = await asyncio.gather(
            TaskQueueService.take_task(t.id, "th-1"),
            TaskQueueService.take_task(t.id, "th-2"),
            return_exceptions=True,
        )
        succeeded = [r for r in results if not isinstance(r, Exception)]
        rejected = [r for r in results if isinstance(r, TaskQueueError)]
        assert len(succeeded) == 1
        assert len(rejected) == 1

        # 成功的那个绑定了 thread
        taken = await TaskQueueService.get_task(succeeded[0].id)
        assert taken.last_thread_id in ("th-1", "th-2")
        assert taken.status == "in_progress"

    async def test_advance_task_proposed_guard(self, _db):
        """advance_task: proposed 状态只能由用户确认（confirm API）"""
        from app.domain.tasks.service import TaskQueueService

        t = await TaskQueueService.create_task(project_id=1, title="p", source="agent")
        with pytest.raises(TaskQueueError, match="confirmed by the user"):
            await TaskQueueService.advance_task(t.id, "pending")

    async def test_advance_task_completed_from_in_progress_redirects(self, _db):
        """in_progress → completed 自动重定向为 self_checked"""
        t = await _mk_task()
        await TaskQueueService.take_task(t.id, "th-1")

        t = await TaskQueueService.advance_task(t.id, "completed", result="")
        assert t.status in ("waiting_acceptance", "completed")

    async def test_advance_task_completed_requires_result_from_waiting(self, _db):
        """waiting_acceptance → completed 仍要求 result"""
        t = await _mk_task()
        await TaskQueueService.take_task(t.id, "th-1")
        await TaskQueueService.advance_task(t.id, "self_checked", result="done")

        with pytest.raises(TaskQueueError, match="result"):
            await TaskQueueService.advance_task(t.id, "completed", result="")

    async def test_advance_task_self_checked_to_waiting(self, _db):
        """in_progress -> self_checked -> waiting_acceptance (T1/T2)"""
        t = await _mk_task(risk_level="T2")
        await TaskQueueService.take_task(t.id, "th-1")

        t = await TaskQueueService.advance_task(
            t.id, "self_checked", result="done", self_check={"verdict": "pass"}
        )
        assert t.status == "waiting_acceptance"
        assert t.self_check == {"verdict": "pass"}

    async def test_advance_task_t3_auto_complete(self, _db):
        """T3/T4 self_checked -> 直接 completed"""
        t = await _mk_task(risk_level="T3")
        await TaskQueueService.take_task(t.id, "th-1")

        t = await TaskQueueService.advance_task(t.id, "self_checked", result="ok")
        assert t.status == "completed"
        assert t.acceptance is not None
        assert t.acceptance["verdict"] == "accepted"

    async def test_advance_task_rejected_feedback(self, _db):
        """submit_acceptance rejected -> 回 pending + acceptance 保存 feedback"""
        t = await _mk_task(risk_level="T2")
        await TaskQueueService.take_task(t.id, "th-1")
        await TaskQueueService.advance_task(t.id, "self_checked", result="done")

        t = await TaskQueueService.submit_acceptance(
            t.id, by="user", verdict="rejected", feedback="wrong"
        )
        assert t.status == "pending"
        assert t.acceptance["verdict"] == "rejected"
        assert t.acceptance["feedback"] == "wrong"

    async def test_requeue_stuck_task_limit(self, _db):
        """requeue_stuck_task: 超过上限转 failed"""
        from sqlalchemy import update

        from app.domain.tasks.service import TaskQueueService
        from app.infrastructure.database.sql.database import session_scope

        t = await _mk_task()
        await TaskQueueService.take_task(t.id, "th-1")
        # 手动置 requeue_count = 3
        async with session_scope() as session:
            await session.execute(
                update(ProjectTask).where(ProjectTask.id == t.id)
                .values(task_data={"requeue_count": 3})
            )

        t = await TaskQueueService.requeue_stuck_task(t.id, "test reason")
        assert t.status == "failed"
        assert (t.task_data or {}).get("requeue_count", 0) == 4

    async def test_require_in_project(self, _db):
        """require_in_project: 同项目通过，跨项目抛异常"""
        t = await _mk_task(project_id=1)
        TaskQueueService.require_in_project(t, 1)  # 同项目

        with pytest.raises(TaskQueueError, match="another project"):
            TaskQueueService.require_in_project(t, 2)

    async def test_dashboard_empty(self, _db):
        """dashboard 空库返回空聚合"""
        from app.domain.tasks.schemas import DashboardPayload

        payload = await TaskQueueService.dashboard(project_id=None)
        assert isinstance(payload, DashboardPayload)
        assert payload.counts == {}
        assert payload.duty_state == "idle"

    async def test_dashboard_with_data(self, _db):
        """dashboard 有数据"""
        t = await _mk_task(title="t1", project_id=1)
        await _mk_task(project_id=1)
        await TaskQueueService.take_task(t.id, "th-1")

        payload = await TaskQueueService.dashboard(project_id=1)
        assert payload.counts.get("pending", 0) >= 1
        assert payload.counts.get("in_progress", 0) >= 1
        assert payload.duty_state == "busy"

    async def test_dashboard_project_filter(self, _db):
        """dashboard 支持 project 过滤"""
        await _mk_task(title="p1")
        await _mk_task(project_id=2, title="p2")

        await TaskQueueService.dashboard(project_id=1)  # 不抛异常即通过

    async def test_dashboard_awaiting_human(self, _db):
        """dashboard 聚合 awaiting_human（仅 in_progress 任务）"""
        from app.infrastructure.database.sql.database import session_scope
        from app.models import HumanRequest

        t = await _mk_task()
        await TaskQueueService.take_task(t.id, "th-1")
        # 任务保持 in_progress（未推进到 self_checked），在该线程上挂起 HumanRequest
        # 使用已知的 thread_id "th-1"（take_task 时传入的），避免对象未刷新导致 last_thread_id 为 None
        async with session_scope() as session:
            from app.models import HumanRequest
            session.add(HumanRequest(
                id=f"hr-{t.id}",
                thread_id="th-1",
                type="confirmation",
                status="pending",
                description="verify",
            ))

        payload = await TaskQueueService.dashboard(project_id=1)
        assert len(payload.awaiting_human) >= 1
        # 验证关联到正确的任务
        assert payload.awaiting_human[0]["task_id"] == t.id


class TestEditTask:
    """edit_task 完整覆盖"""

    async def test_edit_title_description(self, _db):
        """修改标题/描述"""
        t = await _mk_task(title="old", desc="old")
        t = await TaskQueueService.edit_task(t.id, title="new", description="new desc")
        assert t.title == "new"
        assert t.description == "new desc"

    async def test_edit_priority_risk(self, _db):
        """修改优先级/风险"""
        t = await _mk_task(priority="low", risk_level="T4")
        t = await TaskQueueService.edit_task(t.id, priority="urgent", risk_level="T1")
        assert t.priority == "urgent"
        assert t.risk_level == "T1"

    async def test_edit_type_recurring(self, _db):
        """type 变更 + trigger_spec -> recurring"""
        t = await _mk_task(type="once")
        t = await TaskQueueService.edit_task(t.id, trigger_spec="interval:3600")
        assert t.type == "recurring"
        assert t.trigger_spec == "interval:3600"

    async def test_edit_cancel(self, _db):
        """cancel: 仅允许非终态"""
        t = await _mk_task(title="old", desc="old")
        t = await TaskQueueService.edit_task(t.id, title="new", description="new desc")
        assert t.title == "new"
        assert t.description == "new desc"

        # 终态不可 cancel：先完成任务（T2 风险级，需完整流转到 completed）
        t2 = await _mk_task(risk_level="T2")
        await TaskQueueService.take_task(t2.id, "th-1")
        t2 = await TaskQueueService.advance_task(t2.id, "self_checked", result="done", self_check={"verdict": "pass"})
        t2 = await TaskQueueService.advance_task(t2.id, "completed", result="done")
        with pytest.raises(TaskQueueError):
            await TaskQueueService.edit_task(t2.id, cancel=True)

    async def test_edit_cancel_cascades_subtree(self, _db):
        """取消根任务 → 整棵子树级联取消；终态子任务跳过但仍下钻。"""
        from app.domain.tasks.service import TaskQueueService

        root = await _mk_task(title="root")
        child_a = await TaskQueueService.create_task(
            project_id=1, title="child-a", parent_id=root.id
        )
        child_b = await TaskQueueService.create_task(
            project_id=1, title="child-b", parent_id=root.id
        )
        grand = await TaskQueueService.create_task(
            project_id=1, title="grand", parent_id=child_a.id
        )
        # child_b 已完成（终态）→ 跳过取消，但其孙任务（非终态）仍应被级联
        done_grand = await TaskQueueService.create_task(
            project_id=1, title="done-grand", parent_id=child_b.id
        )
        await TaskQueueService.advance_task(done_grand.id, "cancelled", by="user")

        await TaskQueueService.edit_task(root.id, cancel=True)

        assert (await _get_task(root.id)).status == "cancelled"
        assert (await _get_task(child_a.id)).status == "cancelled"
        assert (await _get_task(child_b.id)).status == "cancelled"
        assert (await _get_task(grand.id)).status == "cancelled"
        assert (await _get_task(done_grand.id)).status == "cancelled"

    async def test_edit_dependencies_validated(self, _db):
        """画布连线持久化：依赖替换式更新 + 服务端边界校验。"""
        from app.domain.tasks.service import TaskQueueError, TaskQueueService

        a = await _mk_task(title="a")
        b = await _mk_task(title="b")

        # 正常连线：b 依赖 a
        t = await TaskQueueService.edit_task(b.id, dependencies=[a.id])
        assert (t.dependencies or []) == [a.id]

        # 自依赖拒绝
        with pytest.raises(TaskQueueError, match="depend on itself"):
            await TaskQueueService.edit_task(b.id, dependencies=[b.id])

        # 不存在的依赖拒绝
        with pytest.raises(TaskQueueError, match="not found"):
            await TaskQueueService.edit_task(
                b.id, dependencies=["00000000-0000-0000-0000-000000000000"]
            )

        # 跨项目依赖拒绝
        other = await _mk_task(title="other", project_id=999)
        with pytest.raises(TaskQueueError, match="cross-project"):
            await TaskQueueService.edit_task(b.id, dependencies=[other.id])

        # 环依赖拒绝：清空后建 a→b，再让 b→a 成环
        await TaskQueueService.edit_task(b.id, dependencies=[])
        await TaskQueueService.edit_task(a.id, dependencies=[b.id])
        with pytest.raises(TaskQueueError, match="cycle"):
            await TaskQueueService.edit_task(b.id, dependencies=[a.id])

        # 清空依赖合法
        cleared = await TaskQueueService.edit_task(b.id, dependencies=[])
        assert (cleared.dependencies or []) == []




# pytest 运行入口
if __name__ == "__main__":
    pytest.main([__file__, "-v"])



class TestGlobalMasterSwitch:
    """托盘总闸：全局 enabled=false → 队列不排空（用户心智：停止值守=什么都不跑）。"""

    def _patch_engine(self, monkeypatch, captured: dict, tmp_path):
        from types import SimpleNamespace

        from app.core.engine.dispatch import DispatchStatus

        async def _fake_dispatch(**kwargs):
            captured.setdefault("dispatches", []).append(kwargs)
            return SimpleNamespace(
                status=DispatchStatus.QUEUED, inputs={"messages": []}, error=None
            )

        async def _fake_run(thread_id, _inputs):
            from app.domain.tasks.service import TaskQueueService

            task_id = captured["dispatches"][-1]["metadata"]["source_task_id"]
            await TaskQueueService.take_task(task_id, thread_id)

        monkeypatch.setattr(
            "app.core.engine.dispatch.dispatch_agent_run", _fake_dispatch
        )
        monkeypatch.setattr(
            "app.core.engine.agent.run_agent_background", _fake_run
        )
        monkeypatch.setattr(
            "app.core.engine.capability_profiles.list_domains", lambda _: []
        )
        import json as _json

        proj_dir = tmp_path / "project-1"
        (proj_dir / ".evoloop").mkdir(parents=True)
        (proj_dir / ".evoloop" / "project.json").write_text(
            _json.dumps({"customer_service_duty": {"enabled": True}})
        )

        async def _fake_gpp(*_a, **_k):
            return str(proj_dir)

        monkeypatch.setattr("app.core.project.utils.get_project_path", _fake_gpp)
        monkeypatch.setattr(
            "app.core.channel.duty.config.get_project_path", _fake_gpp
        )

    async def test_global_off_blocks_dispatch(self, _db, monkeypatch, tmp_path):
        from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

        captured: dict = {}
        self._patch_engine(monkeypatch, captured, tmp_path)

        async def _fake_cfg(_pid):
            return {"enabled": True}  # 项目分闸开着

        monkeypatch.setattr(
            "app.core.channel.duty.config.load_duty_config", _fake_cfg
        )
        def _fake_global_cfg():
            return {"enabled": False}  # 总闸关着

        monkeypatch.setattr(
            "app.core.channel.duty.config.load_global_duty_config", _fake_global_cfg
        )

        await _mk_task(due_at=utcnow() - timedelta(minutes=1))
        await dispatch_due_tasks()
        assert not captured.get("dispatches")  # 总闸关 → 零派发

    async def test_global_on_dispatches(self, _db, duty_enabled, monkeypatch, tmp_path):
        from app.domain.tasks.runtime.dispatcher import dispatch_due_tasks

        captured: dict = {}
        self._patch_engine(monkeypatch, captured, tmp_path)

        def _fake_global_cfg():
            return {"enabled": True}

        monkeypatch.setattr(
            "app.core.channel.duty.config.load_global_duty_config", _fake_global_cfg
        )

        tid = (await _mk_task(due_at=utcnow() - timedelta(minutes=1))).id
        await dispatch_due_tasks()
        assert any(
            d["metadata"].get("source_task_id") == tid
            for d in captured.get("dispatches", [])
        )
