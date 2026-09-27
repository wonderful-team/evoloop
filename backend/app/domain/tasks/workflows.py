from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from sqlalchemy import select, update

from app.domain.tasks.constants import (
    WORKFLOW_LIVE_TASK_STATUSES,
    WORKFLOW_SPAWNABLE_STATUSES,
)
from app.domain.tasks.events import (
    publish_task_queue_event,
    publish_workflow_event,
)
from app.domain.tasks.roles import GROWTH_WORKFLOW_ROLES
from app.domain.tasks.schemas import WorkflowStageSpec
from app.domain.tasks.service import TaskQueueService
from app.infrastructure.database.sql.database import session_scope
from app.models.project import ProjectTask
from app.models.task_workflow import TaskArtifact, TaskWorkflow
from app.utils.id import gen_uuid
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    pass


def _validate_trigger_spec(trigger_spec: str) -> None:
    """触发器严格校验（SchedulerService 对非法 spec 静默兜底 +1h，编排层
    不接受这种隐式语义——周期写错就该被拒绝而不是变成每小时跑）。"""
    from croniter import croniter

    if croniter.is_valid(trigger_spec):
        return
    if trigger_spec.startswith("interval:"):
        try:
            int(trigger_spec.split(":")[1])
            return
        except (IndexError, ValueError):
            pass
    raise WorkflowError(
        f"invalid trigger_spec: {trigger_spec!r} (cron or 'interval:<seconds>')"
    )


def _validate_stage_template(
    stages: list[WorkflowStageSpec],
) -> list[WorkflowStageSpec]:
    """阶段模板校验：key 非空唯一、deps 引用存在、无环、且模板顺序为拓扑序
    （spawn 按模板顺序创建，deps 必须先于引用者落行）。"""
    if not stages:
        raise WorkflowError("stage template must contain at least one stage")
    keys = [s.key for s in stages]
    if any(not k.strip() for k in keys):
        raise WorkflowError("stage key must not be empty")
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        raise WorkflowError(f"duplicate stage key(s): {dupes}")
    key_set = set(keys)
    for stage in stages:
        if stage.key in stage.deps:
            raise WorkflowError(f"stage {stage.key} cannot depend on itself")
        unknown = [d for d in stage.deps if d not in key_set]
        if unknown:
            raise WorkflowError(
                f"stage {stage.key} deps reference unknown stage(s): {unknown}"
            )
    # Kahn 拓扑：入度归零计数，处理不完 = 成环
    indegree = dict.fromkeys(keys, 0)
    adjacency: dict[str, list[str]] = {k: [] for k in keys}
    for stage in stages:
        for dep in stage.deps:
            indegree[stage.key] += 1
            adjacency[dep].append(stage.key)
    ready = [k for k, d in indegree.items() if d == 0]
    seen = 0
    while ready:
        current = ready.pop()
        seen += 1
        for nxt in adjacency[current]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if seen != len(keys):
        raise WorkflowError("stage template contains a dependency cycle")
    # spawn 按模板顺序创建行，依赖任务的 id 只有先创建才拿得到 → 强制拓扑序
    order_index = {k: i for i, k in enumerate(keys)}
    for stage in stages:
        for dep in stage.deps:
            if order_index[dep] > order_index[stage.key]:
                raise WorkflowError(
                    f"stage template order violates deps: '{dep}' must be "
                    f"listed before '{stage.key}'"
                )
    return stages


class WorkflowService:
    @staticmethod
    def _growth_stage_description(role, goal: str, inputs: dict[str, Any]) -> str:
        """growth 角色模板 → 通用阶段任务的可执行指令（阶段九.6）。

        旧 EvoloopAgentRuntimeAdapter 专路（build_task_prompt + JSON 产物
        解析 + artifact 落库）退役后，角色 system_prompt 与结构化产出契约
        进 description；上游产出交接由 dispatcher 的 _build_upstream_context
        注入（同轮上游 last_result）；执行协议走标准 tasks 工具行为。
        """
        parts = [role.system_prompt, "", "## 工作流上下文", f"- 工作流目标：{goal}"]
        if inputs:
            import json as _json

            inputs_line = _json.dumps(inputs, ensure_ascii=False)
            parts.append(f"- 工作流输入：{inputs_line}")
        parts += [
            "",
            "## 产出契约（最终回复必须满足）",
            "最终回复必须是一个可直接 json.loads 的 JSON 对象：第一个字符必须是 {，"
            "最后一个字符必须是 }；不得包含 Markdown、说明文字或前后缀。字段为："
            '{"summary": string, "data": object, "risks": string[], "recommendation": string}。'
            "summary 和 recommendation 必须是字符串，data 必须是对象，risks 必须是字符串数组；"
            "四个键都必须存在。上游任务的结论摘要在系统注入的「上游任务产出」一节，直接引用，勿重复调研。",
            "",
            "## 执行协议",
            "先用 tasks 工具 take 认领本任务，用 plan 工具生成计划；完成后 tasks 工具 "
            "update_status(self_checked) 提交结构化结论（result 字段 = 你的 summary）。",
        ]
        return "\n".join(parts)

    @staticmethod
    async def create_growth_workflow(
        *,
        project_id: int,
        member_id: int = 0,
        title: str,
        goal: str,
        inputs: dict[str, Any] | None = None,
    ) -> tuple[TaskWorkflow, list[ProjectTask]]:
        """Text-only commerce growth workflow（阶段九.6 收敛：通用轮次机制）。

        roles.py 降级为模板数据源（stage/system_prompt/风险档/依赖链），
        不再有专属执行器：建单 = 通用 create_workflow（proposed）→ confirm
        （armed，一次性无触发器）→ spawn_round（实例化 5 个普通阶段任务，
        workflow_round=1）。派发/门控/评审/护栏与所有任务同一路径。
        """
        title = title.strip()
        goal = goal.strip()
        if not title:
            raise WorkflowError("title is required")
        if not goal:
            raise WorkflowError("goal is required")

        safe_inputs = inputs or {}
        stage_template = [
            WorkflowStageSpec(
                key=role.stage,
                title=role.title,
                description=WorkflowService._growth_stage_description(
                    role, goal, safe_inputs
                ),
                category="growth_workflow",
                priority="high",
                risk_level=role.risk_level,
                deps=[GROWTH_WORKFLOW_ROLES[i - 1].stage] if i > 0 else [],
            )
            for i, role in enumerate(GROWTH_WORKFLOW_ROLES)
        ]
        workflow = await WorkflowService.create_workflow(
            project_id=project_id,
            member_id=member_id,
            title=title,
            goal=goal,
            origin_thread_id=None,
            stages=stage_template,
        )
        # 一次性 growth 流水线：建单即确认上膛并实例化第一轮（无触发器，
        # 跑完即收口——与旧路径「pending + due_at=now」的即时启动语义等价）
        await WorkflowService.confirm_workflow(workflow.id)
        tasks = await WorkflowService.spawn_round(workflow.id)
        return await WorkflowService.get_workflow(workflow.id), tasks

    @staticmethod
    async def get_workflow(
        workflow_id: str, *, project_id: int | None = None
    ) -> TaskWorkflow:
        async with session_scope() as session:
            result = await session.execute(
                select(TaskWorkflow).where(TaskWorkflow.id == workflow_id)
            )
            workflow = result.scalar_one_or_none()
        if workflow is None:
            raise WorkflowError("workflow not found")
        if project_id is not None and workflow.project_id != project_id:
            raise WorkflowError("workflow not found")
        return workflow

    @staticmethod
    async def list_workflows(
        project_id: int | None, *, member_id: int | None = None, limit: int = 20
    ) -> list[TaskWorkflow]:
        """工作流历史（``project_id=None`` 全量；多租户无项目时按归属过滤）。"""
        async with session_scope() as session:
            stmt = (
                select(TaskWorkflow)
                .order_by(TaskWorkflow.created_at.desc(), TaskWorkflow.id.desc())
                .limit(limit)
            )
            if project_id is not None:
                stmt = stmt.where(TaskWorkflow.project_id == project_id)
            elif member_id is not None:
                stmt = stmt.where(TaskWorkflow.member_id == member_id)
            return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def list_tasks(
        workflow_id: str, *, project_id: int | None = None
    ) -> list[ProjectTask]:
        await WorkflowService.get_workflow(workflow_id, project_id=project_id)
        async with session_scope() as session:
            stmt = select(ProjectTask).order_by(
                ProjectTask.created_at.asc(), ProjectTask.id.asc()
            )
            stmt = stmt.where(ProjectTask.workflow_id == workflow_id)
            if project_id is not None:
                stmt = stmt.where(ProjectTask.project_id == project_id)
            return list((await session.execute(stmt)).scalars().all())

    @staticmethod
    async def list_artifacts(
        workflow_id: str, *, project_id: int | None = None
    ) -> list[TaskArtifact]:
        await WorkflowService.get_workflow(workflow_id, project_id=project_id)
        async with session_scope() as session:
            result = await session.execute(
                select(TaskArtifact)
                .where(TaskArtifact.workflow_id == workflow_id)
                .order_by(TaskArtifact.created_at.asc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def refresh_status(workflow_id: str) -> None:
        tasks = await WorkflowService.list_tasks(workflow_id)
        if not tasks:
            return  # proposed/armed 尚无阶段任务，保持人工态
        statuses = {task.status for task in tasks}
        if tasks and statuses == {"completed"}:
            status = "completed"
        elif "failed" in statuses or "cancelled" in statuses:
            status = "failed"
        elif "waiting_acceptance" in statuses:
            status = "waiting_acceptance"
        else:
            status = "running"
        async with session_scope() as session:
            current = (
                await session.execute(
                    select(TaskWorkflow).where(TaskWorkflow.id == workflow_id)
                )
            ).scalar_one()
            if current.status == status or current.status == "cancelled":
                return  # cancelled 是人工终态，不被聚合覆盖
            current.status = status
        await publish_workflow_event(
            workflow_id,
            event="workflow_status_changed",
            status=status,
        )

    # ── 通用周期工作流（轮次化：触发/编排/执行三分离） ──────────
    # 触发器住 workflow（不再用 recurring 任务冒充编排者）；每轮按模板
    # 实例化阶段 ProjectTask（workflow_round 标轮，dedup 幂等）；轮次间
    # skip-on-busy 绝不并发。阶段任务就是普通队列任务——claim/熔断/
    # 评审/acceptance 全链路复用，无任何特权路径。

    @staticmethod
    def _stage_template(workflow: TaskWorkflow) -> list[WorkflowStageSpec]:
        raw = (workflow.inputs or {}).get("stage_template") or []
        stages = [WorkflowStageSpec.model_validate(item) for item in raw]
        return _validate_stage_template(stages)

    @staticmethod
    async def list_live_tasks(workflow_id: str) -> list[ProjectTask]:
        """未终态的阶段任务（skip-on-busy 与 cancel 的判定集合）。"""
        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        select(ProjectTask).where(
                            ProjectTask.workflow_id == workflow_id,
                            ProjectTask.status.in_(WORKFLOW_LIVE_TASK_STATUSES),
                        )
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)

    @staticmethod
    async def list_round_tasks(workflow_id: str, round_no: int) -> list[ProjectTask]:
        async with session_scope() as session:
            rows = (
                (
                    await session.execute(
                        select(ProjectTask)
                        .where(
                            ProjectTask.workflow_id == workflow_id,
                            ProjectTask.workflow_round == round_no,
                        )
                        .order_by(ProjectTask.created_at.asc(), ProjectTask.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)

    @staticmethod
    async def create_workflow(
        *,
        project_id: int,
        member_id: int = 0,
        title: str,
        goal: str,
        trigger_spec: str | None = None,
        origin_thread_id: str | None = None,
        stages: list[WorkflowStageSpec] | None = None,
    ) -> TaskWorkflow:
        """通用周期工作流提案（status=proposed，等 /confirm 上膛）。

        模板（stages）与周期（trigger_spec）都住本表；确认后由
        supervisor 每拍 spawn_due_rounds 实例化轮次。执行顺序由阶段
        dependencies（同轮真实任务 id）门控——不存在"根任务驱动子任务"
        这类系统不提供的语义。
        """
        title = title.strip()
        goal = goal.strip()
        if not title:
            raise WorkflowError("title is required")
        if not goal:
            raise WorkflowError("goal is required")
        normalized = [WorkflowStageSpec.model_validate(s) for s in (stages or [])]
        _validate_stage_template(normalized)
        if trigger_spec:
            _validate_trigger_spec(trigger_spec)

        inputs: dict[str, Any] = {}
        if origin_thread_id:
            inputs["origin_thread_id"] = origin_thread_id
        inputs["stage_template"] = [s.model_dump() for s in normalized]
        workflow = TaskWorkflow(
            id=gen_uuid(),
            project_id=project_id,
            member_id=member_id,
            title=title,
            goal=goal,
            workflow_type="staged_pipeline",
            status="proposed",
            inputs=inputs,
            trigger_spec=trigger_spec,
            round_no=0,
        )
        async with session_scope() as session:
            session.add(workflow)
            await session.flush()
        await publish_workflow_event(
            workflow.id, event="workflow_created", status=workflow.status
        )
        return workflow

    @staticmethod
    async def confirm_workflow(workflow_id: str) -> TaskWorkflow:
        """用户确认编排提案：proposed → armed（触发器上膛，下轮时刻就位）。"""
        workflow = await WorkflowService.get_workflow(workflow_id)
        if workflow.status != "proposed":
            raise WorkflowError(
                f"workflow {workflow_id} is {workflow.status}, not proposed"
            )
        next_run_at = None
        if workflow.trigger_spec:
            from app.infrastructure.scheduler.service import SchedulerService

            next_run_at = SchedulerService.calculate_next_run(
                workflow.trigger_spec, utcnow()
            )
        async with session_scope() as session:
            current = (
                await session.execute(
                    select(TaskWorkflow).where(TaskWorkflow.id == workflow_id)
                )
            ).scalar_one()
            current.status = "armed"
            current.next_run_at = next_run_at
        await publish_workflow_event(
            workflow_id, event="workflow_confirmed", status="armed"
        )
        if next_run_at is not None:
            from app.domain.tasks.runtime.wakeup import notify_duty_wakeup

            notify_duty_wakeup()
        return await WorkflowService.get_workflow(workflow_id)

    @staticmethod
    async def cancel_workflow(workflow_id: str) -> TaskWorkflow:
        """取消工作流：切断触发器 + 终态化全部在飞阶段任务（含 agent stop）。"""
        workflow = await WorkflowService.get_workflow(workflow_id)
        if workflow.status == "cancelled":
            return workflow
        live = await WorkflowService.list_live_tasks(workflow_id)
        async with session_scope() as session:
            current = (
                await session.execute(
                    select(TaskWorkflow).where(TaskWorkflow.id == workflow_id)
                )
            ).scalar_one()
            current.status = "cancelled"
            current.next_run_at = None
        for stage in live:
            async with session_scope() as session:
                await session.execute(
                    update(ProjectTask)
                    .where(
                        ProjectTask.id == stage.id,
                        ProjectTask.status.notin_(("completed", "failed", "cancelled")),
                    )
                    .values(status="cancelled", version=ProjectTask.version + 1)
                )
            if stage.last_thread_id:
                try:
                    from app.core.engine.session.manager import session_manager

                    await session_manager.stop_agent(
                        stage.last_thread_id, "workflow_cancelled"
                    )
                except Exception:
                    logger.warning(
                        "[WorkflowService] stop agent failed for stage %s",
                        stage.id,
                        exc_info=True,
                    )
            fresh = await TaskQueueService.get_task(stage.id)
            if fresh is not None:
                await publish_task_queue_event(
                    fresh, event="task_advanced", extra={"reason": "workflow_cancelled"}
                )
        await publish_workflow_event(
            workflow_id, event="workflow_cancelled", status="cancelled"
        )
        from app.domain.tasks.runtime.wakeup import notify_duty_wakeup

        notify_duty_wakeup()
        return await WorkflowService.get_workflow(workflow_id)

    @staticmethod
    def _to_utc(dt):
        """naive 视为 UTC；aware 归一 UTC（due 判定统一入口）。"""
        if dt is None:
            return None
        if getattr(dt, "tzinfo", None) is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    async def spawn_due_rounds() -> int:
        """supervisor 每拍调用：到点且空闲的周期工作流实例化新一轮。

        skip-on-busy：任一历史轮仍有活任务 → 本拍不 spawn，next_run_at
        保持到期，空闲后下一拍立即补跑（同日追赶，不丢轮次）。
        """
        now = utcnow()
        async with session_scope() as session:
            # 不能用 SQL 侧 next_run_at <= now 比较：SQLite DateTime 列
            # 实际存的是 ISO-8601 字符串（带 T 分隔与 +00:00 后缀），
            # 与 datetime 参数绑定值的字符串比较永不命中 → armed 工作流
            # 永远不实例化（2026-09-25 全量测试实测）。Python 侧判定。
            rows = (
                (
                    await session.execute(
                        select(TaskWorkflow).where(
                            TaskWorkflow.trigger_spec.isnot(None),
                            TaskWorkflow.next_run_at.isnot(None),
                            TaskWorkflow.status.in_(WORKFLOW_SPAWNABLE_STATUSES),
                        )
                    )
                )
                .scalars()
                .all()
            )
        rows = [w for w in rows if WorkflowService._to_utc(w.next_run_at) <= now]
        spawned = 0
        for workflow in rows:
            try:
                if await WorkflowService.list_live_tasks(workflow.id):
                    continue
                created = await WorkflowService.spawn_round(workflow.id)
                if created:
                    spawned += 1
                    logger.info(
                        "[WorkflowService] round spawned (workflow=%s, round=%s, stages=%d)",
                        workflow.id,
                        int(workflow.round_no or 0) + 1,
                        len(created),
                    )
            except Exception:
                logger.exception(
                    "[WorkflowService] spawn round failed (workflow=%s)", workflow.id
                )
        return spawned

    @staticmethod
    async def spawn_round(workflow_id: str) -> list[ProjectTask]:
        """按模板实例化一轮阶段任务（dedup 幂等；轮次号单调递增）。

        周期工作流由 supervisor spawn_due_rounds 驱动；一次性工作流（无
        trigger_spec，如 growth）由 confirm/create 流程手动 spawn 首轮，
        跑完即收口——无 next_run_at 推进。
        """
        workflow = await WorkflowService.get_workflow(workflow_id)
        template = WorkflowService._stage_template(workflow)
        round_no = int(workflow.round_no or 0) + 1
        # 幂等：同轮已实例化（spawn 中途崩溃后重查）→ 返回已有阶段任务
        existing = await WorkflowService.list_round_tasks(workflow_id, round_no)
        if existing:
            return existing
        created_by_key: dict[str, ProjectTask] = {}
        tasks: list[ProjectTask] = []
        for stage in template:
            dep_ids = [
                created_by_key[dep].id for dep in stage.deps if dep in created_by_key
            ]
            task = await TaskQueueService.create_task(
                project_id=workflow.project_id,
                title=stage.title,
                description=stage.description or "",
                source="user",
                source_ref={
                    "kind": "workflow_round",
                    "workflow_id": workflow.id,
                    "round": round_no,
                    "stage": stage.key,
                },
                category=stage.category,
                priority=stage.priority,
                risk_level=stage.risk_level,
                dependencies=dep_ids,
                workflow_id=workflow.id,
                workflow_round=round_no,
                member_id=workflow.member_id,
                dedup_key=f"wf:{workflow.id}:{round_no}:{stage.key}",
            )
            created_by_key[stage.key] = task
            tasks.append(task)
        async with session_scope() as session:
            current = (
                await session.execute(
                    select(TaskWorkflow).where(TaskWorkflow.id == workflow_id)
                )
            ).scalar_one()
            current.round_no = round_no
            current.status = "running"
            if workflow.trigger_spec:
                from app.infrastructure.scheduler.service import SchedulerService

                current.next_run_at = SchedulerService.calculate_next_run(
                    workflow.trigger_spec, utcnow()
                )
        await publish_workflow_event(
            workflow_id,
            event="round_spawned",
            status="running",
            extra={"round": round_no},
        )
        return tasks
