from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from app.domain.tasks.events import publish_workflow_event
from app.domain.tasks.roles import GROWTH_WORKFLOW_ROLES, workflow_role
from app.domain.tasks.service import (
    TaskQueueService,
    task_dependencies,
    task_title,
    task_workflow_id,
)
from app.infrastructure.database.sql.database import session_scope
from app.models.planning import Plan as PlanRow
from app.models.planning import PlanStep as PlanStepRow
from app.models.project import ProjectTask
from app.models.task_workflow import TaskArtifact, TaskWorkflow
from app.utils.id import gen_uuid
from app.utils.time import utcnow


class WorkflowError(Exception):
    pass


class WorkflowService:
    @staticmethod
    async def create_growth_workflow(
        *,
        project_id: int,
        member_id: int = 0,
        title: str,
        goal: str,
        inputs: dict[str, Any] | None = None,
    ) -> tuple[TaskWorkflow, list[ProjectTask]]:
        title = title.strip()
        goal = goal.strip()
        if not title:
            raise WorkflowError("title is required")
        if not goal:
            raise WorkflowError("goal is required")

        safe_inputs = inputs or {}
        previous_task_id: str | None = None
        tasks: list[ProjectTask] = []

        async with session_scope() as session:
            workflow = TaskWorkflow(
                id=gen_uuid(),
                project_id=project_id,
                member_id=member_id,
                title=title,
                goal=goal,
                status="running",
                inputs=safe_inputs,
            )
            session.add(workflow)
            await session.flush()

            for role in GROWTH_WORKFLOW_ROLES:
                dependencies = [previous_task_id] if previous_task_id else []
                task = ProjectTask(
                    id=gen_uuid(),
                    project_id=project_id,
                    member_id=member_id,
                    status="pending",
                    progress=0,
                    description=goal,
                    task_data={
                        "workflow_stage": role.stage,
                        "workflow_role": role.role,
                        "workflow_runtime": "evoloop",
                        "dependencies": dependencies,
                        "output_artifact_type": role.output_artifact_type,
                        "allowed_packages": list(role.allowed_packages),
                        "candidate_id": str(safe_inputs.get("candidate_id") or "default"),
                    },
                    title=role.title,
                    priority="high",
                    category="growth_workflow",
                    dependencies=dependencies,
                    workflow_id=workflow.id,
                    source="user",
                    source_ref={
                        "kind": "workflow",
                        "workflow_id": workflow.id,
                        "stage": role.stage,
                    },
                    risk_level=role.risk_level,
                    due_at=utcnow(),
                )
                session.add(task)
                await session.flush()
                tasks.append(task)
                previous_task_id = task.id

        return workflow, tasks

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
        project_id: int, *, limit: int = 20
    ) -> list[TaskWorkflow]:
        async with session_scope() as session:
            result = await session.execute(
                select(TaskWorkflow)
                .where(TaskWorkflow.project_id == project_id)
                .order_by(TaskWorkflow.created_at.desc(), TaskWorkflow.id.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

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
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
        return [row for row in rows if row.workflow_id == workflow_id]

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
    async def build_task_prompt(task: ProjectTask) -> str:
        task_data = task.task_data or {}
        workflow_id = str(task_workflow_id(task) or "")
        stage = str(task_data.get("workflow_stage") or "")
        role = workflow_role(stage)
        dependencies = task_dependencies(task)

        upstream: list[dict[str, Any]] = []
        if dependencies:
            async with session_scope() as session:
                result = await session.execute(
                    select(TaskArtifact).where(TaskArtifact.task_id.in_(dependencies))
                )
                artifacts = list(result.scalars().all())
            upstream = [
                {
                    "artifact_id": artifact.id,
                    "stage": artifact.stage,
                    "artifact_type": artifact.artifact_type,
                    "summary": artifact.summary,
                    "data": artifact.data,
                }
                for artifact in artifacts
            ]

        workflow = await WorkflowService.get_workflow(workflow_id)
        payload = json.dumps(
            {
                "goal": workflow.goal,
                "inputs": workflow.inputs,
                "upstream_artifacts": upstream,
            },
            ensure_ascii=False,
        )
        return (
            f"{role.system_prompt}\n\n"
            "以下是工作流输入和上游 Artifact 摘要：\n"
            f"{payload}\n\n"
            "最终回复必须是一个可直接 json.loads 的 JSON 对象：第一个字符必须是 {，"
            "最后一个字符必须是 }；不得包含 Markdown、说明文字或前后缀。字段为："
            '{"summary": string, "data": object, "risks": string[], "recommendation": string}。'
            "summary 和 recommendation 必须是字符串，data 必须是对象，risks 必须是字符串数组；"
            "四个键都必须存在。"
        )

    @staticmethod
    async def ensure_task_plan(task: ProjectTask, thread_id: str) -> None:
        """Persist the deterministic plan for a workflow task without overwriting Agent plans."""
        async with session_scope() as session:
            existing = (
                await session.execute(select(PlanRow).where(PlanRow.thread_id == thread_id))
            ).scalar_one_or_none()
            if existing:
                return
            title = str(task_title(task) or task.id)
            plan_id = gen_uuid()
            steps = [
                ("加载上游 Artifact 与工作流输入", "读取依赖产物并合并工作流目标。"),
                ("生成结构化产物", "调用 Evoloop Agent 生成本阶段产出。"),
                ("校验输出契约", "校验 summary/data/risks/recommendation 四个契约键。"),
            ]
            session.add(
                PlanRow(
                    id=plan_id,
                    thread_id=thread_id,
                    task_id=task.id,
                    title=f"{title}执行计划",
                    status="active",
                )
            )
            for order, (step_title, description) in enumerate(steps):
                session.add(
                    PlanStepRow(
                        id=gen_uuid(),
                        plan_id=plan_id,
                        title=step_title,
                        description=description,
                        status="in_progress" if order == 0 else "pending",
                        order=order,
                    )
                )

    @staticmethod
    async def complete_task_plan(
        task_id: str, thread_id: str | None, result: str
    ) -> None:
        if not thread_id:
            return
        async with session_scope() as session:
            plan = (
                await session.execute(select(PlanRow).where(PlanRow.thread_id == thread_id))
            ).scalar_one_or_none()
            if plan is None or plan.task_id != task_id:
                return
            steps = list(
                (
                    await session.execute(
                        select(PlanStepRow)
                        .where(PlanStepRow.plan_id == plan.id)
                        .order_by(PlanStepRow.order.asc())
                    )
                ).scalars()
            )
            for step in steps:
                step.status = "completed"
                step.result = result
            plan.status = "completed"

    @staticmethod
    async def complete_task(
        task: ProjectTask,
        *,
        result: str,
        output: dict[str, Any],
        thread_id: str | None = None,
    ) -> TaskArtifact:
        task_data = task.task_data or {}
        workflow_id = str(task_workflow_id(task) or "")
        if not isinstance(output, dict):
            raise WorkflowError("structured output must be a JSON object")
        required_keys = ("summary", "data", "risks", "recommendation")
        missing_keys = [key for key in required_keys if key not in output]
        if missing_keys:
            raise WorkflowError(
                f"structured output missing contract keys: {missing_keys}"
            )
        updated_task = await TaskQueueService.advance_task(
            task.id,
            "self_checked",
            result=result,
            self_check={
                "verdict": "pass",
                "checks": [
                    {
                        "name": "structured_output",
                        "pass": True,
                        "evidence": result[:500],
                    }
                ],
                "deviations": [],
            },
            thread_id=thread_id or task.last_thread_id,
        )

        artifact_id = gen_uuid()
        summary = str(output.get("summary") or result[:500])
        async with session_scope() as session:
            session.add(
                TaskArtifact(
                    id=artifact_id,
                    project_id=updated_task.project_id,
                    workflow_id=workflow_id,
                    task_id=updated_task.id,
                    stage=str(task_data.get("workflow_stage") or ""),
                    artifact_type=str(task_data.get("output_artifact_type") or "Unknown"),
                    status="generated",
                    version=1,
                    summary=summary,
                    data={"output": output},
                )
            )
            await session.flush()

        artifact = await WorkflowService.get_artifact(artifact_id)
        if artifact is None:
            raise WorkflowError("artifact was not persisted")
        await WorkflowService.complete_task_plan(
            updated_task.id,
            thread_id or updated_task.last_thread_id,
            result,
        )
        await publish_workflow_event(
            workflow_id,
            event="artifact_created",
            task_id=updated_task.id,
            stage=str(task_data.get("workflow_stage") or ""),
            status=updated_task.status,
            extra={"artifact_id": artifact.id},
        )
        await WorkflowService.refresh_status(workflow_id)
        return artifact

    @staticmethod
    async def get_artifact(artifact_id: str) -> TaskArtifact | None:
        async with session_scope() as session:
            result = await session.execute(
                select(TaskArtifact).where(TaskArtifact.id == artifact_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def refresh_status(workflow_id: str) -> None:
        tasks = await WorkflowService.list_tasks(workflow_id)
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
            if current.status == status:
                return
            current.status = status
        await publish_workflow_event(
            workflow_id,
            event="workflow_status_changed",
            status=status,
        )
