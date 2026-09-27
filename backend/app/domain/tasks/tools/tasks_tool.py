"""tasks facade tool — single entry for the autonomous task queue (stage 1).

[risk:T3][confirm:false][read_before:tasks list][verify_after:tasks list]
Writes follow the T1-T4 acceptance policy: T1/T2 tasks must reach
waiting_acceptance and pass user acceptance (submit_acceptance); T3/T4
auto-complete after self_check.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Annotated, Any, Literal

from app.core.engine.message.native_classes import RunnableConfig
from app.core.tools import evoloop_tool
from app.core.tools.base import InjectedToolArg
from app.domain.tasks.service import (
    TaskQueueError,
    TaskQueueService,
    task_category,
    task_dependencies,
    task_number,
    task_priority,
    task_title,
)

logger = logging.getLogger(__name__)


def _context_project_id() -> int | None:
    """当前执行上下文的项目（全局模式 None 不设限）。"""
    from app.core.context.manager import ContextManager

    return ContextManager.current().project_id


# ---------------------------------------------------------------------------
# Facade tool (single entry, action dispatch; aligned with plan/todo facades)
# ---------------------------------------------------------------------------

# [risk:T3][confirm:false][read_before:tasks list][verify_after:tasks list]
# Writes follow the T1-T4 acceptance policy: T1/T2 tasks must reach
# waiting_acceptance and pass user acceptance (submit_acceptance); T3/T4
# auto-complete after self_check.


@evoloop_tool(
    name="tasks",
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.tasks",
)
async def tasks(
    action: Literal[
        "list",
        "create",
        "take",
        "update",
        "update_status",
        "create_workflow",
    ] = "list",
    task_id: str | None = None,
    status: str | None = None,
    target_status: Literal[
        "self_checked", "waiting_acceptance", "failed"
    ] | None = None,
    category: str | None = None,
    title: str | None = None,
    description: str | None = None,
    task_type: Literal["once", "recurring"] | None = None,
    priority: Literal["low", "medium", "high", "urgent"] | None = None,
    risk_level: Literal["T1", "T2", "T3", "T4"] | None = None,
    due_at: str | None = None,
    trigger_spec: str | None = None,
    source: Literal["user", "agent", "external"] | None = None,  # noqa: ARG001
    parent_id: str | None = None,
    dependencies: list[str] | None = None,
    tags: list[Any] | None = None,
    acceptance_criteria: list[Any] | None = None,
    stages_json: str | None = None,
    root_only: bool = False,
    result: str | None = None,
    self_check: str | None = None,
    limit: int = 20,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """Autonomous task queue (single entry, action dispatch).

    Actions:
    - list: view the queue. status/category/due/root_only filters; default = executable set.
    - create: create a task. source=agent creates a PROPOSED task (user confirms
      in the task list); source=user creates directly as pending.
      Supports parent_id and dependencies for subtask decomposition and DAG ordering.
    - take: claim a pending task (pending → in_progress). First action of a run
      working a task; binds the workspace thread.
    - update_status: advance status (in_progress → self_checked → waiting_acceptance,
      or failed). Use `target_status` (NOT `status`) for this action.
      `completed` is NOT a valid target; the backend auto-redirects it to
      `self_checked`. `self_check` is the structured JSON report.
    - create_workflow: propose a RECURRING PIPELINE (每日/周期流水线的唯一正确
      形态)。stages_json = JSON array of {key, title, description, priority,
      risk_level, deps:[stage keys]}（拓扑序）；trigger_spec = cron 或
      interval:秒。编排住工作流：确认后每轮自动实例化阶段任务。禁止再用
      "recurring 根任务 + 依赖子任务"表达周期流水线（无编排语义，必坏）。
    - submit_acceptance: RESERVED for the user API — the agent must NOT call it
      (acceptance verdicts are never self-recorded; reach waiting_acceptance via
      update_status instead).

    WHEN TO USE:
    - As a duty/wakeup run: list → take → work (plan attached via plan tool) →
      update_status(self_checked) → submit to waiting_acceptance.
    - On discovering new work inside any run: action=create with source=agent
      (a PROPOSED task; do NOT insert it into the current batch). Proposal
      discipline: check `list` for an existing same-topic proposal first;
      max ~3 proposals per run (excess goes into the closing summary);
      rejected proposals return feedback via `list` — do not re-propose
      the same thing.
    - Recurring pipelines: create_workflow ONLY (never recurring task with
      children). T1/T2 tasks never bypass acceptance. Do not fabricate status.

    Args:
        action: one of list / create / take / update_status / create_workflow.
        task_id: target task (take / update_status).
        status: list filter, or legacy target status for update_status (prefer target_status).
        target_status: required for update_status; one of self_checked / waiting_acceptance / failed.
        category: list filter / creation category (e.g. orders, goods, stock).
        title / description: creation fields (workflow: description = goal).
        priority: low / medium / high / urgent.
        risk_level: T1-T4 (inherited from tool risk annotations).
        due_at: ISO datetime for one-shot due time.
        trigger_spec: cron or "interval:<seconds>" for recurring tasks.
        stages_json: JSON array [{key,title,description,priority,risk_level,deps}].
        source: creator semantics — user / agent (proposed) / external.
        result: what this step did and its outcome (required to complete).
        self_check: JSON string {verdict, checks:[{name,pass,evidence}], deviations}.
        limit: list page size (max 50).
    """
    thread_id = config.get("configurable", {}).get("thread_id") if config else None
    limit = max(1, min(int(limit), 50))

    try:
        if action == "list":
            from app.core.context.manager import ContextManager

            rows = await TaskQueueService.list_tasks(
                status=status,
                category=category,
                project_id=ContextManager.current().project_id,
                root_only=root_only,
                limit=limit,
            )
            items = [
                {
                    "id": t.id,
                    "task_no": task_number(t),
                    "title": task_title(t),
                    "status": t.status,
                    "category": task_category(t),
                    "priority": task_priority(t),
                    "risk": t.risk_level,
                    "parent_id": t.parent_id,
                    "dependencies": task_dependencies(t),
                    "due_at": (t.due_at or t.next_run_at).isoformat()
                    if (t.due_at or t.next_run_at)
                    else None,
                    "source": t.source,
                    "instruction": t.description or "",
                    # 被拒返工的验收反馈：Agent 据此修正，而不是盲跑重试
                    "feedback": (t.acceptance or {}).get("feedback"),
                    "requeue_count": (t.task_data or {}).get("requeue_count", 0),
                }
                for t in rows
            ]
            return json.dumps({"items": items, "count": len(items)}, ensure_ascii=False)

        if action == "create":
            from app.core.context.manager import ContextManager

            pid = ContextManager.current().project_id
            if pid is None:
                return json.dumps({"error": "project context required"})
            if not title:
                return json.dumps({"error": "title required"})
            # 来源是服务端事实，不由模型自报（审计 P1-03）：工具面只可能
            # 被 Agent 调用 → 一律 source=agent（proposed 待确认）。模型传
            # source="user" 伪装人工通道绕过提案闸的口子就此封死。
            src = "agent"

            origin_task_id = None
            if src == "agent":
                origin_task_id = getattr(
                    ContextManager.current(), "current_task_id", None
                )
            resolved_parent_id = parent_id
            if not resolved_parent_id and src == "agent" and origin_task_id:
                resolved_parent_id = origin_task_id

            parsed_due = None
            if due_at:
                parsed_due = datetime.fromisoformat(due_at)
            # 编排表达力红线（2026-09-25 #T-1 事故）：队列没有"编排"原语，
            # recurring 任务每天驱动的是它自己的描述，驱动不了任何子任务。
            # 因此 recurring 与任务图（parent/dependencies）互斥——周期流水线
            # 必须走工作流提案（/tasks/workflows API），错误信息显式指路。
            if trigger_spec or task_type == "recurring":
                if resolved_parent_id or dependencies:
                    return json.dumps(
                        {
                            "error": "recurring 任务不能携带 parent_id/dependencies"
                            "（recurring 只驱动自身，无编排语义）。周期流水线请"
                            "通过工作流提案创建：stages + trigger_spec 一个"
                            "工作流对象，确认后每轮自动实例化阶段任务。"
                        },
                        ensure_ascii=False,
                    )
            resolved_dependencies = [str(d) for d in (dependencies or [])]
            for ref_id in (
                [resolved_parent_id] if resolved_parent_id else []
            ) + resolved_dependencies:
                upstream = await TaskQueueService.get_task(str(ref_id))
                if upstream is not None and upstream.trigger_spec:
                    return json.dumps(
                        {
                            "error": "上游任务是 recurring（不产生 completed 终态），"
                            "不能作为依赖/父任务参与任务图。周期编排请改用"
                            "工作流提案（/tasks/workflows API）。"
                        },
                        ensure_ascii=False,
                    )
            # origin thread 记录（评审者会话）：agent 与 user 两条路径都有
            # 对话上下文，都要能回到创建它的对话里；无 thread 但有 origin
            # task 时保留任务链追踪（agent_run）
            if thread_id:
                create_ref = {
                    "kind": "message",
                    "ref": thread_id,
                    **({"task_id": origin_task_id} if origin_task_id else {}),
                }
            elif origin_task_id:
                create_ref = {"kind": "agent_run", "task_id": origin_task_id}
            else:
                create_ref = {}
            task = await TaskQueueService.create_task(
                project_id=int(pid),
                title=title,
                description=description or "",
                type=task_type or "once",
                source=src,
                source_ref=create_ref,
                category=category,
                priority=priority or "medium",
                risk_level=risk_level,
                due_at=parsed_due,
                trigger_spec=trigger_spec,
                parent_id=resolved_parent_id,
                dependencies=resolved_dependencies,
                tags=tags,
                acceptance_criteria=acceptance_criteria,
            )
            return json.dumps(
                {
                    "success": True,
                    "id": task.id,
                    "task_no": task_number(task),
                    "parent_id": task.parent_id,
                    "status": task.status,
                    "note": "proposed: awaiting user confirmation"
                    if task.status == "proposed"
                    else None,
                },
                ensure_ascii=False,
            )

        if action == "update":
            """Edit title / description / priority / risk / type of a task."""
            if not task_id:
                return json.dumps({"error": "task_id required"})
            task = await TaskQueueService.get_task(task_id)
            if task is None:
                return json.dumps({"error": f"task {task_id} not found"})
            TaskQueueService.require_in_project(task, _context_project_id())
            try:
                fresh = await TaskQueueService.edit_task(
                    task_id,
                    title=title,
                    description=description,
                    priority=priority,
                    risk_level=risk_level,
                    task_type=task_type,
                    trigger_spec=trigger_spec,
                )
            except TaskQueueError as e:
                return json.dumps({"error": str(e)})
            return json.dumps(
                {"success": True, "id": fresh.id, "status": fresh.status},
                ensure_ascii=False,
            )

        if action == "take":
            if not task_id or not thread_id:
                return json.dumps({"error": "task_id required"})
            task = await TaskQueueService.get_task(task_id)
            if task is None:
                return json.dumps({"error": f"task {task_id} not found"})
            TaskQueueService.require_in_project(task, _context_project_id())
            task = await TaskQueueService.take_task(task_id, thread_id)
            return json.dumps(
                {
                    "success": True,
                    "id": task.id,
                    "status": task.status,
                    "title": task_title(task),
                    "instruction": task.description or "",
                },
                ensure_ascii=False,
            )

        if action == "update_status":
            resolved_status = target_status or status
            if not task_id or not resolved_status:
                return json.dumps({"error": "task_id and target_status/status required"})
            current = await TaskQueueService.get_task(task_id)
            if current is not None:
                TaskQueueService.require_in_project(current, _context_project_id())
            parsed_check = json.loads(self_check) if self_check else None
            task = await TaskQueueService.advance_task(
                task_id,
                resolved_status,
                result=result,
                self_check=parsed_check,
                thread_id=thread_id,
            )
            payload: dict[str, Any] = {
                "success": True,
                "id": task.id,
                "status": task.status,
            }
            if task.trigger_spec and task.status == "pending":
                # recurring 自检回队：本轮已完结，防止 agent 把 pending 误读为
                # 失败而反复硬推（实测 33 次 illegal transition 烧轮次）
                payload["note"] = (
                    "recurring 任务本轮已完结并回队——self_checked 是本轮终态，"
                    "下次执行由 trigger_spec(next_run_at) 推进，请勿再 update_status"
                )
            return json.dumps(payload, ensure_ascii=False)

        if action == "create_workflow":
            # 周期流水线的唯一正确形态：工作流提案（proposed，等用户 confirm）
            import json as _json

            from app.core.context.manager import ContextManager
            from app.domain.tasks.schemas import WorkflowStageSpec
            from app.domain.tasks.workflows import WorkflowError, WorkflowService

            pid = ContextManager.current().project_id
            if pid is None:
                return json.dumps({"error": "project context required"})
            if not title:
                return json.dumps({"error": "title required"})
            if not trigger_spec:
                return json.dumps(
                    {"error": "trigger_spec required (cron or interval:seconds)"}
                )
            try:
                raw_stages = _json.loads(stages_json or "[]")
                stages = [
                    WorkflowStageSpec(
                        key=str(s.get("key") or ""),
                        title=str(s.get("title") or ""),
                        description=str(s.get("description") or ""),
                        category=s.get("category"),
                        priority=str(s.get("priority") or "medium"),
                        risk_level=s.get("risk_level"),
                        deps=[str(d) for d in (s.get("deps") or [])],
                    )
                    for s in raw_stages
                ]
                workflow = await WorkflowService.create_workflow(
                    project_id=int(pid),
                    title=title,
                    goal=description or "",
                    trigger_spec=trigger_spec,
                    origin_thread_id=thread_id or None,
                    stages=stages,
                )
            except (WorkflowError, _json.JSONDecodeError) as e:
                return json.dumps({"error": str(e)}, ensure_ascii=False)
            return json.dumps(
                {
                    "success": True,
                    "workflow_id": workflow.id,
                    "status": workflow.status,
                    "note": "workflow proposal: awaiting user confirmation; 每轮将自动实例化阶段任务",
                },
                ensure_ascii=False,
            )

        if action == "submit_acceptance":
            # acceptance belongs to the user API, never the agent
            return json.dumps(
                {"error": "acceptance is reserved for the user API, not the agent"}
            )

        return json.dumps({"error": f"unknown action '{action}'"})
    except TaskQueueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("tasks facade failed: %s", e)
        return json.dumps({"error": str(e)})
