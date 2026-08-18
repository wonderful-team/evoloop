import logging
import time
from typing import Any

from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.engine.message.native_classes import BaseMessage, SystemMessage
from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.nodes.prompts import SupervisorContext, SupervisorPromptBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.schemas import EngineResult
from app.core.engine.state import AgentState, StateUpdate
from app.core.tools.manager import tool_manager
from app.i18n.service import i18n
from app.infrastructure.database import session_scope

logger = logging.getLogger(__name__)


class SupervisorNode(BaseAgentNode):
    """
    Supervisor Node - Decision-making hub for the EvoLoop Agent.
    """

    def __init__(self):
        super().__init__(node_name="Supervisor", max_steps=settings.SUPERVISOR_AGENT_MAX_STEPS, temperature=0.2)

    @staticmethod
    def _filter_messages_for_supervisor(messages: list[BaseMessage]) -> list[BaseMessage]:
        result: list[BaseMessage] = []
        latest_ticket_idx = -1
        latest_tool_idx = -1

        for i, msg in enumerate(messages):
            if msg.role == "user" and msg.name == "context_ticket":
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
                if m.role != "assistant" or not getattr(m, "tool_calls", None):
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
            elif role == "user":
                if msg.name == "context_ticket":
                    if i == latest_ticket_idx:
                        result.append(msg)
                else:
                    result.append(msg)
            elif role == "assistant":
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
            if msg.role == "assistant" and not getattr(msg, "tool_calls", None):
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

    async def prepare_state(self, state: AgentState, config: dict) -> StateUpdate | None:
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
                logger.warning(f"[Supervisor] Failed to consume queued signal: {e}. Clearing entry.", exc_info=True)
                return StateUpdate(pending_signals=remaining)

        state.messages = self._filter_messages_for_supervisor(state.messages)

        from app.core.engine.state.lifecycle import StateLifecycleManager

        StateLifecycleManager.consume_next_node(state)
        StateLifecycleManager.consume_blocked_by_hook(state)

        await self._emit_status(config, i18n.get("supervisor.status_analyzing"))

        worker_outcome = StateLifecycleManager.consume_worker_outcome(state)
        if worker_outcome:
            logger.info(f"[Supervisor] Worker returned '{worker_outcome}'. Delegating review to Supervisor LLM.")
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
                or "The current environment cannot verify macro outcomes."
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
                warning_msg = (
                    "[SYSTEM NOTE] The previous Worker execution reported that the outcome "
                    "is unverifiable due to environment limitations:\n\n"
                    f"{reason[:600]}\n\n"
                    "ACCEPT this report and respond to the user. "
                    "Do NOT dispatch another Worker for verification."
                )
                state.messages.append(SystemMessage(content=warning_msg))
                logger.info("[Supervisor] Worker reported unverifiable outcome; flagged and instructed to accept.")
            elif worker_outcome in ("truncated", "failed", "error", "incomplete"):
                warning_msg = (
                    f"[SYSTEM ALERT] The previous Worker execution was {worker_outcome.upper()}.\n"
                    "If TRUNCATED: The worker hit its step limit before finishing. You MUST review the progress and issue a new `route_to` ticket to continue the work.\n"
                    "If FAILED/ERROR/INCOMPLETE: Review the last tool errors and decide whether to retry or formulate a new plan.\n"
                    "DO NOT return an empty response. You must take explicit action."
                )
                state.messages.append(SystemMessage(content=warning_msg))

            # Preserve the Worker's final plaintext report for context so the
            # Supervisor does not mistakenly re-route after the Worker has concluded.
            if worker_outcome in ("success", "done") and final_report:
                preserve_msg = (
                    "[SYSTEM NOTE] The Worker has returned the following final report. "
                    "ACCEPT the report and respond to the user if it already answers the mission. "
                    "Do NOT dispatch another Worker for verification unless the report is incomplete.\n\n"
                    f"{final_report[:800]}"
                )
                state.messages.append(SystemMessage(content=preserve_msg))

        return None

    async def build_prompt_pair(self, state: AgentState, config: dict) -> tuple[str, str]:
        project_id = state.project_id if state.project_id is not None else DEFAULT_PROJECT_ID
        messages = state.messages

        context = await self._build_context(state, config, messages, project_id)
        prompt_builder = SupervisorPromptBuilder(
            project_id=project_id,
            iteration_count=context.iteration_count,
            context=context,
        )
        static_system_prompt = await prompt_builder.build(config)
        dynamic_context_ticket = await prompt_builder.build_context_ticket(config, session_goal=state.session_goal)

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
        if last_msg and last_msg.role == "assistant":
            ai_content = str(last_msg.content).strip()

        if ai_content:
            if (
                last_msg.additional_kwargs.get("is_truncated")
                and original_state.worker_outcome == "truncated"
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
            thread_id = original_state.thread_id or config.get("configurable", {}).get("thread_id")
            if not thread_id:
                raise ValueError("Cannot self-publish SessionCompletedEvent without thread_id")
            event_data = SessionCompletedData(
                thread_id=thread_id,
                summary=ai_content,
                tts_summary=ai_content if source == "voice" else "",
                outcome="completed",
                source=source,
                model=ctx.active_model,
                duration_ms=(time.time() - _direct_start) * 1000,
            )
            logger.info("[Supervisor] Direct response → self-publishing SessionCompletedEvent")
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
        from app.models.planning import Plan as DBPlan
        from app.models.planning import PlanStep as DBPlanStep

        thread_id = state.thread_id or config.get("configurable", {}).get("thread_id")
        if not thread_id:
            return

        async with session_scope() as session:
            stmt = select(DBPlan).where(
                DBPlan.thread_id == thread_id, DBPlan.status == "active"
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
                if step.status == "in_progress":
                    step.status = "completed"
                    step.result = "Completed via signal queue dispatch."
                    break

            for step in steps:
                if step.status in ("pending",):
                    step.status = "in_progress"
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
