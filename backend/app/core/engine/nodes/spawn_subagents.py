"""SpawnSubagentsNode — launch N parallel subagent executions (Worker-primitive bodies).

Design: docs/subagent-design.md §4.1 / §6.1.
"""

import asyncio
import json
import logging
import time

from app.core.engine.background_agent.models import BackgroundAgentInputs
from app.core.engine.message.native_classes import HumanMessage
from app.core.engine.nodes.base import BaseNode
from app.core.engine.nodes.utils.subagent_manager import recover_subagent_state
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.config import AgentRuntimeConfig, ExecutionTicket
from app.core.engine.worker_registry import worker_registry
from app.models.subagent import SubagentRun

logger = logging.getLogger(__name__)

MAX_PARALLEL = 5

# 模块级集合持有 done_callback 的 task 引用，防止被 gc 提前回收。
_done_callback_tasks: set[asyncio.Task] = set()


class SpawnSubagentsNode(BaseNode):
    """并行拉起 N 个 subagent 执行，每个有独立 thread_id 和 AgentState。"""

    def __init__(self):
        super().__init__(node_name="SpawnSubagents")

    async def __call__(self, state: AgentState, config: dict) -> StateUpdate:
        plan = state.subagent_plan
        if not plan or not plan.get("subtasks"):
            logger.warning("[SpawnSubagents] No subagent plan found")
            return StateUpdate(next_node=RoutingTarget.SUPERVISOR)

        parent_tid = state.thread_id or config.get("configurable", {}).get("thread_id", "")
        # split 模式（Worker 裂变）：subagent 的 run parent 与会话隔离，避免
        # 完成事件唤醒会话 Supervisor（Worker 自己等待/聚合）；前端生命周期
        # 事件仍走会话 thread（lifecycle_tid）。
        split_mode = bool(plan.get("split_mode"))
        run_parent_tid = f"{parent_tid}-split" if split_mode else parent_tid
        selected = plan["subtasks"][:MAX_PARALLEL]

        active = list(state.active_subagents or [])
        historical_context = self._build_historical_context(state)
        spawned = 0
        skipped = 0
        for idx, subtask in enumerate(selected):
            sub_tid = f"{run_parent_tid}-sub-{idx}"
            subagent_id = subtask.get("id", f"sub-{idx}")

            # 防重派护栏：该 thread_id 已有 SubagentRun（崩溃恢复后重派、或 LLM
            # 重复 route 同类）时跳过，避免 thread_id UNIQUE 冲突炸掉会话主循环。
            if await self._subagent_run_exists(sub_tid):
                skipped += 1
                logger.warning(
                    f"[SpawnSubagents] {sub_tid} already has a SubagentRun; "
                    "skip re-spawn to avoid UNIQUE collision"
                )
                continue

            # 1. Persist SubagentRun (run parent isolates worker splits).
            await self._create_subagent_run(
                subagent_id, run_parent_tid, sub_tid, subtask
            )

            # 2. Build child ticket + state (carry parent conversation context).
            child_ticket = self._build_child_ticket(
                state, subtask, historical_context=historical_context
            )
            child_state = AgentState(
                thread_id=sub_tid,
                project_id=state.project_id,
                messages=[HumanMessage(content=subtask["instruction"])],
                ticket=child_ticket,
                session_goal=subtask["instruction"],
            )

            # 3. Build BackgroundAgentInputs (task_type="subagent").
            inputs = self._build_child_inputs(config, child_state, subtask, subagent_id)

            # 4. Launch lightweight execution body (Worker-primitive ReAct loop).
            from app.core.engine.background_agent import run_subagent_background

            task = asyncio.create_task(run_subagent_background(sub_tid, inputs))

            # 5. Register for cancellation.
            await worker_registry.register_worker(
                sub_tid, task, description=subtask["instruction"][:50]
            )

            # 6. Publish public lifecycle event (frontend live subagent panel).
            from app.core.events import system_bus
            from app.core.events.schemas.subagent import SubagentLifecycleEvent

            await system_bus.publish(
                SubagentLifecycleEvent(
                    thread_id=parent_tid,
                    subagent_id=subagent_id,
                    subagent_thread_id=sub_tid,
                    instruction=subtask["instruction"],
                    status="started",
                )
            )

            # 7. done_callback (holds task ref to prevent gc).
            self._schedule_done_callback(
                task, subagent_id, sub_tid, run_parent_tid,
                lifecycle_tid=parent_tid,
            )

            active.append(
                {
                    # subagent_id 使用 run thread id（即 sub_tid），与
                    # subagent_runs.thread_id / SSE subagent_thread_id / DB 恢复
                    # 三方 key 保持一致，避免与事件去重错位。
                    "subagent_id": sub_tid,
                    "thread_id": sub_tid,
                    "instruction": subtask["instruction"],
                    "status": "running",
                    "started_at": time.time(),
                }
            )
            spawned += 1

        # split 模式不设 pending_subagent_aggregation：Worker 自己聚合。
        pending_agg = (
            {
                "strategy": plan.get("aggregation_strategy", "merge"),
                "expected_count": spawned,
                "parent_task": plan.get("parent_task", ""),
            }
            if plan.get("requires_aggregation") and not split_mode and spawned
            else None
        )

        # 打破崩溃后重派死循环：计划内所有 sub_tid 均已存在（被防重派护栏跳过）
        # 且没有新 spawn → 若仍有存活运行行则回 Supervisor 继续等待；否则全部已
        # 终态（崩溃恢复已标 failed/orphaned），直接路由 Aggregate 呈现诚实汇总，
        # 避免 Supervisor 反复要求重派而一次都派不出去。
        if not split_mode and spawned == 0 and skipped > 0:
            reconciled = await recover_subagent_state(parent_tid)
            if reconciled["active_subagents"]:
                logger.info(
                    f"[SpawnSubagents] plan subtasks all exist and "
                    f"{len(reconciled['active_subagents'])} still running; waiting"
                )
                return StateUpdate(
                    active_subagents=reconciled["active_subagents"],
                    subagent_plan=None,
                    next_node=RoutingTarget.SUPERVISOR,
                )
            logger.warning(
                "[SpawnSubagents] plan subtasks already terminal; "
                "routing to aggregate (F1 crash recovery)"
            )
            return StateUpdate(
                completed_subagents=reconciled["completed_subagents"],
                subagent_plan=None,
                pending_subagent_aggregation={
                    "strategy": plan.get("aggregation_strategy", "merge"),
                    "expected_count": len(selected),
                    "parent_task": plan.get("parent_task", ""),
                },
                next_node=RoutingTarget.AGGREGATE_SUBAGENTS,
            )

        return StateUpdate(
            active_subagents=active,
            subagent_plan=None,
            pending_subagent_aggregation=pending_agg,
            next_node=RoutingTarget.SUPERVISOR,
        )

    # ── helpers ────────────────────────────────────────────────

    async def _subagent_run_exists(self, sub_tid: str) -> bool:
        from sqlalchemy import select

        from app.infrastructure.database import session_scope

        async with session_scope() as session:
            result = await session.execute(
                select(SubagentRun.id).where(SubagentRun.thread_id == sub_tid)
            )
            return result.first() is not None

    async def _create_subagent_run(
        self, subagent_id: str, parent_tid: str, sub_tid: str, subtask: dict
    ) -> None:
        from app.infrastructure.database import session_scope

        run = SubagentRun(
            # id 与 thread_id 保持一致（均基于钉死索引），前端 SSE 的
            # subagent_thread_id、父上下文里作为 subagent_id 的 r.id 才会三者一致。
            # LLM 计划的 subtask["id"]（例如 1-based 的 sub-1/2/3）不得污染 run 身份，
            # 否则与 0-based 的 thread_id 错位一位，面板/聚合均对不上。
            id=sub_tid,
            parent_thread_id=parent_tid,
            thread_id=sub_tid,
            instruction=subtask["instruction"],
            role_name=subtask.get("role", "Subagent"),
            focus_paths=json.dumps(subtask.get("focus_paths", [])),
            acceptance_criteria=json.dumps(subtask.get("acceptance_criteria", [])),
            status="running",
        )
        async with session_scope() as session:
            session.add(run)

    def _build_child_ticket(
        self,
        state: AgentState,
        subtask: dict,
        historical_context: str = "",
    ) -> ExecutionTicket:
        """Build the child ExecutionTicket (role / focus / skills only).

        工具排除不在 ticket 层做（agent_config.tools 是追加语义，不会移除工具）。
        工具过滤放在 WorkerNode.get_tools 的 R5 实现（按 ticket_type=="subagent"）。
        """
        parent_ticket = state.ticket
        child_tools = subtask.get("tools") or (
            parent_ticket.agent_config.tools
            if parent_ticket and parent_ticket.agent_config
            else []
        )
        return ExecutionTicket(
            ticket_type="subagent",
            topic=subtask.get("title") or subtask["instruction"][:80],
            acceptance_criteria=subtask.get("acceptance_criteria", []),
            focus_paths=subtask.get("focus_paths", []),
            historical_context=historical_context or None,
            agent_config=AgentRuntimeConfig(
                role_name=subtask.get("role") or "Subagent",
                system_instructions=subtask.get("system_instructions") or "",
                tools=child_tools,
                skill_hint=subtask.get("skill_hint"),
            ),
        )

    @staticmethod
    def _build_historical_context(state: AgentState) -> str:
        """Extract a compact slice of the parent conversation for the subagent.

        Subagents are spawned in parallel with only their own instruction; giving
        them the user's request and the Supervisor's delegation decision keeps
        them grounded in the real conversation context.
        """
        msgs = state.messages or []
        parts = []
        # 最近一条用户消息（用户原话）
        for m in reversed(msgs):
            if m.role == "user":
                content = str(getattr(m, "content", "") or "")
                if content.strip():
                    parts.append(f"User request: {content[:600]}")
                    break
        # 最近一条 assistant 消息（Supervisor 的委派/决策轮）
        for m in reversed(msgs):
            if m.role == "assistant":
                content = str(getattr(m, "content", "") or "")
                if content.strip():
                    parts.append(f"Supervisor: {content[:800]}")
                    break
        return "\n".join(parts)

    def _build_child_inputs(
        self, parent_config: dict, child_state: AgentState, subtask: dict, subagent_id: str
    ) -> BackgroundAgentInputs:
        configurable = parent_config.get("configurable", {})
        metadata = parent_config.get("metadata", {})
        parent_tid = configurable.get("thread_id")
        root_tid = metadata.get("root_thread_id") or parent_tid

        return BackgroundAgentInputs(
            goal=subtask["instruction"],
            session_goal=subtask["instruction"],
            project_id=metadata.get("project_id") or child_state.project_id,
            model=configurable.get("model"),
            working_directory=configurable.get("working_directory"),
            ticket=child_state.ticket,
            messages=[
                m.model_dump() if hasattr(m, "model_dump") else m
                for m in child_state.messages
            ],
            metadata={
                **metadata,
                "task_type": "subagent",
                "subagent_id": subagent_id,
                "parent_thread_id": parent_tid,
                "root_thread_id": root_tid,
                "source": metadata.get("source", ""),
            },
        )

    # ── done_callback ──────────────────────────────────────────

    def _schedule_done_callback(
        self,
        t: asyncio.Task,
        subagent_id: str,
        sub_tid: str,
        parent_tid: str,
        lifecycle_tid: str | None = None,
    ) -> None:
        # 必须在 task 真正完成后才检查其状态：asyncio.Task 未完成时
        # task.exception() 会抛 InvalidStateError（"Exception is not set."），
        # 若立即调度会被 _on_subagent_done 误判为 failed。
        def on_done(_fut: asyncio.Future) -> None:
            cb = asyncio.create_task(
                self._on_subagent_done(
                    parent_tid, subagent_id, sub_tid, t,
                    lifecycle_tid=lifecycle_tid or parent_tid,
                )
            )
            _done_callback_tasks.add(cb)
            cb.add_done_callback(_done_callback_tasks.discard)

        t.add_done_callback(on_done)

    async def _on_subagent_done(
        self,
        parent_tid: str,
        subagent_id: str,
        sub_tid: str,
        task: asyncio.Task,
        lifecycle_tid: str | None = None,
    ) -> None:
        from app.core.events import system_bus
        from app.core.events.schemas.subagent import (
            SubagentCompletedEvent,
            SubagentLifecycleEvent,
        )

        current = await self._get_subagent_run(sub_tid)
        if current and current.status in ("awaiting_a2a", "awaiting_human"):
            return

        if current and current.status == "cancelled":
            status, result, error = "cancelled", "", "Cancelled"
            tools_used = []
        else:
            try:
                if task.cancelled():
                    status, result, error = "cancelled", "", "Cancelled"
                elif task.exception():
                    exc = task.exception()
                    status, result, error = "failed", "", str(exc)
                else:
                    status = "completed"
                    error = None
                    result = (
                        task.result()
                        if isinstance(task.result(), str)
                        else str(task.result() or "")
                    )
            except Exception as e:
                status, result, error = "failed", "", str(e)
            tools_used = []

        await self._update_subagent_run(sub_tid, status, result, error, tools_used)

        await system_bus.publish(
            SubagentCompletedEvent(
                thread_id=parent_tid,
                subagent_id=subagent_id,
                subagent_thread_id=sub_tid,
                status=status,
                result=result,
                error=error,
                tools_used=tools_used,
            )
        )

        # Public lifecycle event: keep the frontend subagent panel in sync.
        # split 模式：内部完成事件走 run parent（隔离），前端事件走会话 thread。
        await system_bus.publish(
            SubagentLifecycleEvent(
                thread_id=lifecycle_tid or parent_tid,
                subagent_id=subagent_id,
                subagent_thread_id=sub_tid,
                instruction=(current.instruction or "") if current else "",
                status=status,
                result=result,
                error=error,
            )
        )
        logger.info(
            f"[SpawnSubagents] Subagent {subagent_id} ({sub_tid}) finished: {status}"
        )

    async def _get_subagent_run(self, thread_id: str):
        from sqlalchemy import select

        from app.infrastructure.database import session_scope

        async with session_scope() as session:
            stmt = select(SubagentRun).where(SubagentRun.thread_id == thread_id)
            return (await session.execute(stmt)).scalar_one_or_none()

    async def _update_subagent_run(
        self, thread_id: str, status: str, result: str,
        error: str | None, tools_used: list,
    ) -> None:
        from datetime import datetime, timezone

        from sqlalchemy import select

        from app.infrastructure.database import session_scope

        async with session_scope() as session:
            stmt = select(SubagentRun).where(SubagentRun.thread_id == thread_id)
            run = (await session.execute(stmt)).scalar_one_or_none()
            if run:
                run.status = status
                run.result = result
                run.error = error
                run.tools_used = json.dumps(tools_used)
                run.completed_at = datetime.now(timezone.utc)
