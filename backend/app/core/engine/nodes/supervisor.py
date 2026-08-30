import logging
import time
from typing import Any

from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.engine.message.constants import MessageRole
from app.core.engine.message.native_classes import AIMessage, BaseMessage, SystemMessage
from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.nodes.prompts import SupervisorContext, SupervisorPromptBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.schemas import EngineResult, WorkerOutcome
from app.core.engine.state import AgentState, StateUpdate
from app.core.tools.manager import tool_manager
from app.i18n.service import i18n
from app.infrastructure.database import session_scope
from app.models.subagent import SubagentStatus
from app.utils.template import render_template
from app.utils.time import elapsed_ms

logger = logging.getLogger(__name__)


class SupervisorNode(BaseAgentNode):
    """
    Supervisor Node - Decision-making hub for the EvoLoop Agent.
    """

    def __init__(self):
        super().__init__(
            node_name="Supervisor",
            max_steps=settings.SUPERVISOR_AGENT_MAX_STEPS,
            temperature=0.2,
        )

    @staticmethod
    def _filter_messages_for_supervisor(
        messages: list[BaseMessage],
    ) -> list[BaseMessage]:
        result: list[BaseMessage] = []
        latest_ticket_idx = -1
        latest_tool_idx = -1

        for i, msg in enumerate(messages):
            if msg.role == MessageRole.HUMAN and msg.name == "context_ticket":
                latest_ticket_idx = i
            if msg.role == "tool":
                latest_tool_idx = i

        # 最新 tool 消息配对的 assistant(tool_calls) 索引：若最新 tool 是其
        # 所属 assistant tool_calls 的结果，保留该 assistant 消息，让 LLM 看到
        # "调用了工具 → 返回结果"的完整闭环，避免 Supervisor 反复重试同一宏。
        keep_assistant_idx = -1
        if latest_tool_idx >= 0:
            latest_tool = messages[latest_tool_idx]
            latest_tool_call_id = getattr(latest_tool, "tool_call_id", None)
            for i in range(latest_tool_idx - 1, -1, -1):
                m = messages[i]
                if m.role != MessageRole.AI or not getattr(m, "tool_calls", None):
                    continue
                ids = [
                    tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                    for tc in m.tool_calls
                ]
                if latest_tool_call_id in ids:
                    keep_assistant_idx = i
                    break

        for i, msg in enumerate(messages):
            role = msg.role
            if role == "system":
                result.append(msg)
            elif role == MessageRole.HUMAN:
                if msg.name == "context_ticket":
                    if i == latest_ticket_idx:
                        result.append(msg)
                else:
                    result.append(msg)
            elif role == MessageRole.AI:
                # 保留无 tool_calls 的普通 assistant 消息，以及最新 tool 结果
                # 配对的 assistant(tool_calls) 消息；其余历史 tool_calls 丢弃。
                if not msg.tool_calls or i == keep_assistant_idx:
                    result.append(msg)
            elif role == "tool" and i == latest_tool_idx:
                result.append(msg)

        dropped = len(messages) - len(result)
        if dropped > 0:
            logger.info(
                f"[Supervisor] Messages filtered: {len(messages)} → {len(result)} "
                f"(dropped={dropped} tool/exec messages)"
            )
        return result

    @staticmethod
    def _extract_final_report(messages: list[BaseMessage]) -> str | None:
        """Return the most recent plaintext assistant report if one exists."""
        for msg in reversed(messages):
            if msg.role == MessageRole.AI and not getattr(msg, "tool_calls", None):
                content = str(getattr(msg, "content", "") or "").strip()
                if len(content) > 30:
                    return content
        return None

    @staticmethod
    def _is_unverifiable_report(report: str) -> bool:
        """
        Lightweight fallback: detect explicit 'cannot verify' language in legacy
        Worker plaintext reports. New code should use `report_outcome` instead.
        """
        if not report:
            return False
        text = report.lower()
        return any(
            phrase in text
            for phrase in (
                "无法验证",
                "verification impossible",
                "unverifiable",
                "无法确认",
                "environment cannot verify",
            )
        )

    async def prepare_state(
        self, state: AgentState, config: dict
    ) -> StateUpdate | None:
        if state.pending_signals:
            import app.core.engine.signals.signals as schemas
            from app.core.engine.signals import signal_manager

            next_sig_dict = state.pending_signals[0]
            remaining = state.pending_signals[1:]

            try:
                sig_type = next_sig_dict.pop("_type", "RouteToSignal")
                SignalClass = getattr(schemas, sig_type, schemas.RouteToSignal)
                signal = SignalClass.model_validate(next_sig_dict)

                dispatch_result = await signal_manager.dispatch(state, signal, config)
                if dispatch_result is not None:
                    dispatch_result.pending_signals = remaining
                    await self._sync_db_plan_step_on_signal_consume(state, config)
                    return dispatch_result
            except Exception as e:
                logger.warning(
                    f"[Supervisor] Failed to consume queued signal: {e}. Clearing entry.",
                    exc_info=True,
                )
                return StateUpdate(pending_signals=remaining)

        state.messages = self._filter_messages_for_supervisor(state.messages)

        from app.core.engine.state.lifecycle import StateLifecycleManager

        StateLifecycleManager.consume_next_node(state)
        StateLifecycleManager.consume_blocked_by_hook(state)

        await self._emit_status(config, i18n.get("supervisor.status_analyzing"))

        worker_outcome = StateLifecycleManager.consume_worker_outcome(state)
        if worker_outcome:
            logger.info(
                f"[Supervisor] Worker returned '{worker_outcome}'. Delegating review to Supervisor LLM."
            )
            # Capture the finished ticket's topic before clearing it; this lets the
            # anti-loop guard associate future verification routes with this target.
            finished_ticket_topic = state.ticket.topic if state.ticket else None
            state.ticket = None

            final_report = self._extract_final_report(state.messages)
            shared = state.shared_context or {}
            reported_status = shared.get("worker_report_status")

            # Primary signal: Worker explicitly reported that verification is impossible.
            is_unverifiable = (
                reported_status == "unverifiable"
                or shared.get("verification_impossible") is True
            )
            # Fallback for legacy plaintext reports.
            if not is_unverifiable and final_report:
                is_unverifiable = self._is_unverifiable_report(final_report)

            reason = (
                shared.get("verification_block_reason")
                or shared.get("worker_report_summary")
                or (final_report[:500] if final_report else "")
            )

            if is_unverifiable:
                blocked_topic = (
                    shared.get("verification_blocked_topic")
                    or finished_ticket_topic
                    or state.session_goal
                    or ""
                )
                blocked_topic = blocked_topic[:500]

                blocked_topics = shared.get("verification_blocked_topics") or []
                if not isinstance(blocked_topics, list):
                    blocked_topics = []
                if blocked_topic and blocked_topic not in blocked_topics:
                    blocked_topics.append(blocked_topic)

                state.shared_context = {
                    **shared,
                    "verification_impossible": True,
                    "verification_block_reason": reason[:500],
                    "verification_blocked_topic": blocked_topic,
                    "verification_blocked_topics": blocked_topics,
                }
                warning_msg = render_template(
                    "core/engine/fragments/supervisor_system_notes.j2",
                    note_type="unverifiable",
                    reason=reason[:600],
                )
                state.messages.append(SystemMessage(content=warning_msg))
                logger.info(
                    "[Supervisor] Worker reported unverifiable outcome; flagged and instructed to accept."
                )
            elif worker_outcome in (
                WorkerOutcome.TRUNCATED,
                WorkerOutcome.FAILED,
                WorkerOutcome.ERROR,
                WorkerOutcome.INCOMPLETE,
            ):
                warning_msg = render_template(
                    "core/engine/fragments/supervisor_system_notes.j2",
                    note_type="worker_outcome",
                    outcome=worker_outcome.upper(),
                )
                state.messages.append(SystemMessage(content=warning_msg))

            # Preserve the Worker's final plaintext report for context so the
            # Supervisor does not mistakenly re-route after the Worker has concluded.
            if worker_outcome in (
                WorkerOutcome.SUCCESS,
                WorkerOutcome.DONE,
                WorkerOutcome.COMPLETED,
            ) and final_report:
                preserve_msg = render_template(
                    "core/engine/fragments/supervisor_system_notes.j2",
                    note_type="preserve_report",
                    report=final_report[:800],
                )
                state.messages.append(SystemMessage(content=preserve_msg))
                logger.info(
                    "[Supervisor] Appended [SYSTEM NOTE] preserving Worker final report."
                )

        # ── Subagent 事件消费（每次 prepare_state 都检查）─────────────────
        # 全部 subagent 终态且满足聚合条件时，短路 Supervisor LLM（否则其纯文本
        # 回复会把 next_node 覆盖为 END，聚合结果不呈现）。
        routed_to_aggregate = await self._consume_subagent_events(state, config)

        # 聚合轮（subagent_completed 唤醒，无用户新消息）且还有 subagent 在跑：
        # 不跑 LLM，直接结束本轮等待下一事件——避免陈旧上下文抢跑
        # （重复委派 / 误 cancel_all_subagents）。
        aggregation_turn = bool(getattr(state, "subagent_aggregation_turn", False))
        if aggregation_turn:
            state.subagent_aggregation_turn = False
            if routed_to_aggregate:
                return StateUpdate(next_node=RoutingTarget.AGGREGATE_SUBAGENTS)
            running = [
                a
                for a in (state.active_subagents or [])
                if a.get("status")
                in (
                    SubagentStatus.RUNNING,
                    SubagentStatus.AWAITING_A2A,
                    SubagentStatus.AWAITING_HUMAN,
                )
            ]
            if running:
                logger.info(
                    f"[Supervisor] Aggregation turn: {len(running)} subagent(s) still "
                    f"running; skipping LLM to wait for terminal states."
                )
                return StateUpdate(next_node=RoutingTarget.END)
        elif routed_to_aggregate:
            return StateUpdate(next_node=RoutingTarget.AGGREGATE_SUBAGENTS)

        # ── 聚合已完成：强制呈现，防 Supervisor LLM 重新委派 ─────────────
        # 聚合节点运行后 presentation_pending 置位但尚未呈现。此时 Supervisor
        # 应直接呈现聚合结果，而非再次发起 subagent / Worker（LLM 在聚合轮
        # 上下文不清晰时检查重复委派）。真正的强制收尾由 _customize_dispatch_result
        # 兜底，这里只注入提示辅助 LLM 输出文案。
        if (
            getattr(state, "presentation_pending", False)
            and not state.pending_subagent_aggregation
            and not state.active_subagents
        ):
            note = render_template(
                "core/engine/fragments/supervisor_system_notes.j2",
                note_type="presentation",
            )
            already = any(
                isinstance(m, SystemMessage)
                and note[:20] in str(getattr(m, "content", ""))
                for m in (state.messages or [])
            )
            if not already:
                state.messages.append(SystemMessage(content=note))
                logger.info(
                    "[Supervisor] Appended [SYSTEM NOTE] presenting aggregate result."
                )

        return None

    # ── Subagent 事件消费（设计文档 §10）────────────────────────────

    async def _consume_subagent_events(self, state: AgentState, config: dict) -> bool:
        """Consume subagent events and decide whether to route to aggregation.

        顺序固定：先 drain HITL 请求（登记路由表 + 注入 prompt），再转发已回答的
        HITL，再做崩溃恢复，最后 drain 完成事件并检查聚合条件（§10）。
        返回 True 表示已路由到聚合节点（调用方应短路 Supervisor LLM）。
        """
        # 1. 消费 SubagentHITLRequestEvent（§5.5 透传登记）
        hitl_requests = await self._drain_subagent_hitl_requests(state)
        for req in hitl_requests:
            sub_tid = req["subagent_thread_id"]
            state.active_subagent_hitl[sub_tid] = req["tool_call_id"]
            existing = {
                p.get("subagent_thread_id")
                for p in (state.pending_subagent_hitl_requests or [])
            }
            if sub_tid not in existing:
                state.pending_subagent_hitl_requests.append(req)
            logger.info(
                f"[Supervisor] Registered subagent HITL passthrough: {sub_tid} "
                f"({req['request_type']})"
            )

        # 2. HITL 透传转发：父主运行刚回答了一个 ask_human（resume_and_persist 已把
        #    答案写回 tool 消息）→ 把答案转发给 awaiting 的 subagent（§5.5）。
        await self._forward_answered_subagent_hitl(state)

        # 3. 崩溃恢复：无条件与 SubagentRun 表调和。进程重启后 worker_registry
        #    为空，running 行的 asyncio task 已死 → recover 立即标 failed/orphaned；
        #    正常运行时 task 存活则不会误回收。注意：新用户轮重建的 state 不会带
        #    pending_subagent_aggregation，若只在「active 为空 & pending 存在」时
        #    恢复，崩溃重启后的首条消息会带着僵尸 running 行直接重派 → thread_id
        #    UNIQUE 冲突炸会话（F1 E2E 实测）。
        from app.core.engine.nodes.utils.subagent_manager import recover_subagent_state

        recovered = await recover_subagent_state(state.thread_id or "")
        if recovered["active_subagents"] or recovered["completed_subagents"]:
            state.active_subagents = recovered["active_subagents"]
            state.completed_subagents = recovered["completed_subagents"]
            logger.info(
                f"[Supervisor] Reconciled {len(recovered['active_subagents'])} active, "
                f"{len(recovered['completed_subagents'])} completed subagents from DB"
            )

        # 4. 消费 SubagentCompletedEvent，更新 active/completed 列表。
        #    去重 key 统一用 subagent_thread_id（= run thread id），与 spawn 的
        #    active 条目、DB 恢复的 subagent_id 一致。
        completed_events = await self._drain_subagent_events(state)
        if completed_events:
            completed_by_id = {
                c.get("subagent_id"): c for c in (state.completed_subagents or [])
            }
            for comp in completed_events:
                completed_by_id[comp["subagent_thread_id"]] = {
                    **comp,
                    "subagent_id": comp["subagent_thread_id"],
                }
                active = [
                    a
                    for a in (state.active_subagents or [])
                    if a.get("subagent_id") != comp["subagent_thread_id"]
                ]
                state.active_subagents = active
            state.completed_subagents = list(completed_by_id.values())
            expected = (state.pending_subagent_aggregation or {}).get(
                "expected_count", 0
            )
            logger.info(
                f"[Supervisor] Consumed {len(completed_events)} subagent completion events. "
                f"Total: {len(state.completed_subagents)}/{expected}"
            )

        # 5. 聚合条件检查：全部到达终态且无挂起 → 路由到 AggregateSubagentsNode。
        return self._maybe_route_to_aggregate(state)

    def _maybe_route_to_aggregate(self, state: AgentState) -> bool:
        """若满足聚合条件，原地设置 next_node=AGGREGATE_SUBAGENTS（§10）。

        返回 True 表示已路由到聚合节点（调用方应短路 Supervisor LLM，
        否则 LLM 的纯文本回复会把 next_node 覆盖为 END，聚合结果不呈现）。
        """
        if not state.pending_subagent_aggregation:
            return False
        pending = state.pending_subagent_aggregation
        expected = pending.get("expected_count", 0)

        terminal_statuses = {
            SubagentStatus.COMPLETED,
            SubagentStatus.FAILED,
            SubagentStatus.CANCELLED,
        }
        completed = [
            c
            for c in (state.completed_subagents or [])
            if c.get("status") in terminal_statuses
        ]
        awaiting = [
            a
            for a in (state.active_subagents or [])
            if a.get("status")
            in (SubagentStatus.AWAITING_A2A, SubagentStatus.AWAITING_HUMAN)
        ]

        if awaiting:
            logger.info(
                f"[Supervisor] {len(awaiting)} subagent(s) awaiting "
                f"(A2A callback / HITL 透传). Not aggregating yet."
            )
            return False

        if len(completed) < expected:
            return False

        need_inputs = [c.get("need_input") for c in completed if c.get("need_input")]
        if need_inputs:
            # Phase B：A2A need_input 需主会话 ask_human，先不回聚合。
            logger.info(
                f"[Supervisor] All subagents terminal, but {len(need_inputs)} "
                f"need user input from A2A. Routing to Supervisor to ask human."
            )
            state.pending_need_inputs = need_inputs
            return False

        logger.info(
            f"[Supervisor] All {expected} subagents done. Routing to AggregateSubagents."
        )
        state.next_node = RoutingTarget.AGGREGATE_SUBAGENTS
        return True

    async def _drain_subagent_events(self, state: AgentState) -> list[dict]:
        """Drain SubagentCompletedEvent for this parent thread."""
        from app.core.engine.nodes.utils.subagent_events import drain_subagent_events

        return await drain_subagent_events(state.thread_id or "")

    async def _drain_subagent_hitl_requests(self, state: AgentState) -> list[dict]:
        """Drain SubagentHITLRequestEvent for this parent thread."""
        from app.core.engine.nodes.utils.subagent_events import (
            drain_subagent_hitl_requests,
        )

        events = await drain_subagent_hitl_requests(state.thread_id or "")
        return [e.model_dump() for e in events]

    async def _forward_answered_subagent_hitl(self, state: AgentState) -> None:
        """父主运行回答 ask_human 后，把答案转发给等待中的 subagent（§5.5）。

        父同一时刻只挂起一个 HITL；pending_subagent_hitl_requests 非空且最近一条
        ask_human tool 消息已含答案时，逐个转发并消费。
        """
        if not (state.pending_subagent_hitl_requests or state.active_subagent_hitl):
            return

        answered_sub_tid = None
        answer = ""
        for msg in reversed(state.messages or []):
            if msg.role != "tool" or getattr(msg, "name", None) != "ask_human":
                continue
            answer = getattr(msg, "content", "") or ""
            if not answer:
                return
            # 找到与最近 ask_human 对应的 pending 透传 subagent（父同时挂一个）。
            answered_sub_tid = state.pending_subagent_hitl_requests[0][
                "subagent_thread_id"
            ]
            break
        if not answered_sub_tid or not answer:
            return

        from app.core.engine.nodes.utils.subagent_hitl import respond_subagent_hitl

        await respond_subagent_hitl(answered_sub_tid, answer)
        state.pending_subagent_hitl_requests = state.pending_subagent_hitl_requests[1:]
        state.active_subagent_hitl.pop(answered_sub_tid, None)
        logger.info(
            f"[Supervisor] Forwarded HITL answer to subagent {answered_sub_tid}"
        )

    async def build_prompt_pair(
        self, state: AgentState, config: dict
    ) -> tuple[str, str]:
        project_id = (
            state.project_id if state.project_id is not None else DEFAULT_PROJECT_ID
        )
        messages = state.messages

        context = await self._build_context(state, config, messages, project_id)
        prompt_builder = SupervisorPromptBuilder(
            project_id=project_id,
            iteration_count=context.iteration_count,
            context=context,
        )
        static_system_prompt = await prompt_builder.build(config)
        dynamic_context_ticket = await prompt_builder.build_context_ticket(
            config, session_goal=state.session_goal
        )

        return static_system_prompt, dynamic_context_ticket

    async def get_tools(self, state: AgentState) -> list[Any]:
        return await tool_manager.get_node_tools("supervisor", state)

    async def _customize_dispatch_result(
        self,
        dispatch_result: StateUpdate,
        original_state: AgentState,
        engine_result: EngineResult,
        config: dict,
    ) -> StateUpdate:
        new_iter_count = (original_state.iteration_count or 0) + 1
        if isinstance(dispatch_result, StateUpdate):
            dispatch_result.iteration_count = new_iter_count

            # 聚合收尾强约束（B2）：presentation_pending 置位且 LLM 仍试图重新
            # 委派（supervisor/spawn/worker 等）时，不进入新的委派循环，而是直接
            # 以聚合结果确定性地收尾呈现给用户。
            if (
                getattr(original_state, "presentation_pending", False)
                and not original_state.pending_subagent_aggregation
                and not original_state.active_subagents
                and dispatch_result.next_node
                in (
                    RoutingTarget.SPAWN_SUBAGENTS,
                    RoutingTarget.WORKER,
                    RoutingTarget.SEQUENTIAL_WORKFLOW,
                )
            ):
                logger.warning(
                    f"[Supervisor] Clamping re-delegation ({dispatch_result.next_node}) "
                    f"after aggregation; presenting aggregate result instead."
                )
                # 设计收敛（B2）：聚合内容由聚合节点确定性写入 last_aggregation_result
                # （aggregate_subagents 内部"LLM 聚合空 → 拼接保底"，必非空），此处只取
                # 该字段，不再逐级扫描候选消息/LLM 文本，也不兜底造文案。契约破损时
                # 该字段为空则不再追加消息（聚合 AIMessage 已在 state.messages 中可见）。
                present = original_state.last_aggregation_result or ""
                if not present:
                    logger.error(
                        "[Supervisor] Clamp found no aggregate content: "
                        "aggregate_subagents contract guarantees non-empty "
                        f"last_aggregation_result, got {present!r}."
                    )
                messages = [AIMessage(content=present)] if present else []

                return StateUpdate(
                    messages=messages,
                    next_node=RoutingTarget.END,
                    presentation_pending=False,
                    last_aggregation_result=present,
                    subagent_aggregation_turn=False,
                    iteration_count=new_iter_count,
                )

            # 非委派路径（END/FINISH/聚合完成）：清除呈现标记，避免影响后续用户轮。
            if dispatch_result.next_node == RoutingTarget.END:
                dispatch_result.presentation_pending = False

            # 保留 Supervisor 派活时的安抚文案：LLM 在调用 route_to 的同时输出
            # 的 assistant 消息（content 如"好的，马上处理"）应一并保留给用户，
            # 而不是被 route_to 信号路径丢弃。Worker 阶段的消息不在此列。
            if dispatch_result.next_node in (
                RoutingTarget.WORKER,
                RoutingTarget.SEQUENTIAL_WORKFLOW,
            ):
                ai_msgs = [
                    m
                    for m in (engine_result.messages or [])
                    if m.name != "context_ticket" and getattr(m, "content", None)
                ]
                if ai_msgs:
                    existing = list(dispatch_result.messages or [])
                    dispatch_result.messages = existing + ai_msgs

        return dispatch_result

    async def _build_fallback_outcome(
        self,
        original_state: AgentState,
        engine_result: EngineResult,
        config: dict,
    ) -> StateUpdate:
        _direct_start = time.time()
        new_iter_count = (original_state.iteration_count or 0) + 1
        new_messages = [
            m for m in (engine_result.messages or []) if m.name != "context_ticket"
        ]
        has_error_msg = any(
            msg.additional_kwargs.get("is_error") for msg in new_messages
        )
        if has_error_msg:
            return StateUpdate(
                messages=new_messages,
                next_node=RoutingTarget.FINISH,
                iteration_count=new_iter_count,
            )

        ai_content = ""
        last_msg = new_messages[-1] if new_messages else None
        if last_msg and last_msg.role == MessageRole.AI:
            ai_content = str(last_msg.content).strip()

        if ai_content:
            if (
                last_msg.additional_kwargs.get("is_truncated")
                and original_state.worker_outcome == WorkerOutcome.TRUNCATED
            ):
                return StateUpdate(
                    messages=new_messages,
                    next_node=RoutingTarget.WORKER,
                    iteration_count=new_iter_count,
                )

            # Direct response without tool calls — no need for Finish audit.
            # Self-publish completion event so the result is pushed immediately.
            from app.core.context.manager import ContextManager
            from app.core.events.publishers import publish_session_completed
            from app.core.events.schemas import SessionCompletedData

            ctx = ContextManager.current()
            source = config.get("metadata", {}).get("source", "")
            thread_id = original_state.thread_id or config.get("configurable", {}).get(
                "thread_id"
            )
            if not thread_id:
                raise ValueError(
                    "Cannot self-publish SessionCompletedEvent without thread_id"
                )
            event_data = SessionCompletedData(
                thread_id=thread_id,
                summary=ai_content,
                tts_summary=ai_content if source == "voice" else "",
                outcome="completed",
                source=source,
                model=ctx.active_model,
                duration_ms=elapsed_ms(_direct_start),
            )
            logger.info(
                "[Supervisor] Direct response → self-publishing SessionCompletedEvent"
            )
            await publish_session_completed(data=event_data)
            return StateUpdate(
                messages=new_messages,
                next_node=RoutingTarget.END,
                summary=ai_content,
            )

        # Empty response (no AI content, no error) → safe fallback
        return StateUpdate(
            messages=new_messages,
            next_node=RoutingTarget.FINISH,
            iteration_count=new_iter_count,
        )

    async def _sync_db_plan_step_on_signal_consume(
        self, state: AgentState, config: dict
    ) -> None:
        from app.domain.planning.constants import PlanStatus, PlanStepStatus
        from app.models.planning import Plan as DBPlan
        from app.models.planning import PlanStep as DBPlanStep

        thread_id = state.thread_id or config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return

        async with session_scope() as session:
            stmt = select(DBPlan).where(
                DBPlan.thread_id == thread_id,
                DBPlan.status == PlanStatus.ACTIVE.value,
            )
            result = await session.execute(stmt)
            db_plan = result.scalar_one_or_none()
            if not db_plan:
                return

            stmt_steps = (
                select(DBPlanStep)
                .where(DBPlanStep.plan_id == db_plan.id)
                .order_by(DBPlanStep.order)
            )
            result_steps = await session.execute(stmt_steps)
            steps = result_steps.scalars().all()

            for step in steps:
                if step.status == PlanStepStatus.IN_PROGRESS.value:
                    step.status = PlanStepStatus.COMPLETED.value
                    step.result = "Completed via signal queue dispatch."
                    break

            for step in steps:
                if step.status in (PlanStepStatus.PENDING.value,):
                    step.status = PlanStepStatus.IN_PROGRESS.value
                    break

            from app.core.events import system_bus
            from app.domain.planning.event import PlanUpdatedEvent

            await system_bus.publish(PlanUpdatedEvent(thread_id=thread_id))

    async def _emit_status(self, config: dict, status: str):
        from app.core.monitoring.activity import activity_monitor

        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        await activity_monitor.update_agent_state(
            thread_id=thread_id,
            mode="PLANNING",
            task_name="Supervisor Decision",
            task_status=status,
        )

    async def _build_context(
        self, state: AgentState, config: dict, messages: list, project_id: int
    ) -> "SupervisorContext":
        core_tools = await self.get_tools(state)
        last_human = ""
        for m in reversed(messages):
            if isinstance(m, dict):
                role = m.get("role")
                name = m.get("name")
                content = m.get("content", "")
            else:
                role = getattr(m, "type", None)
                name = getattr(m, "name", None)
                content = getattr(m, "content", "") or ""
            if role in ("user", "human") and name != "context_ticket":
                last_human = content if isinstance(content, str) else ""
                break

        return SupervisorContext(
            tools=core_tools,
            iteration_count=(state.iteration_count or 0),
            last_human_msg=last_human,
            state=state,
            structured_plan=state.structured_plan or state.current_plan,
        )
