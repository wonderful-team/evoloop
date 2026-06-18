import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.engine.message.utils import get_last_human_message
from app.core.engine.nodes.base import BaseAgentNode
from app.core.engine.nodes.prompts import SupervisorContext, SupervisorPromptBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.schemas import EngineResult
from app.core.engine.state import AgentState, StateUpdate
from app.core.tools.manager import tool_manager
from app.i18n.service import i18n
from app.infrastructure.database.sql.database import session_scope

logger = logging.getLogger(__name__)


def _plan_has_pending_steps(plan: str | dict | None) -> bool:
    """Check if a structured plan has any pending (not done) steps."""
    if not plan:
        return False
    try:
        if isinstance(plan, str):
            plan_data = json.loads(plan)
        else:
            plan_data = plan
        # Support multiple plan schema shapes
        steps = plan_data.get("steps") or plan_data.get("plan", {}).get("steps") or []
        for step in steps:
            status = step.get("status", "").lower()
            if status not in ("done", "completed", "success", "finished"):
                return True
        return False
    except Exception:
        return False


class SupervisorNode(BaseAgentNode):
    """
    Supervisor Node - Decision-making hub for the EvoLoop Agent (LLM-First Architecture).

    Responsibilities:
    1. Sense environment via tools (telemetry, search_native_tools, search_skills)
    2. LLM-driven routing decisions via ReAct loop
    3. Tool authorization via authorized_tools
    4. Context building (tools, memory, project structure)
    """

    def __init__(self):
        super().__init__(node_name="Supervisor", max_steps=settings.SUPERVISOR_AGENT_MAX_STEPS, temperature=0.2)

    @staticmethod
    def _filter_messages_for_supervisor(messages: list[BaseMessage]) -> list[BaseMessage]:
        """
        Supervisor 是决策者，只需要语义层消息：
        - System Prompt
        - 用户原始需求（HumanMessage）
        - 最新的 context_ticket（动态状态注入）
        - 不带 tool_calls 的 AIMessage（Supervisor 自己的思考、Worker 的最终总结）

        完全丢弃所有 tool 调用链（AIMessage with tool_calls + ToolMessage）。
        进度信息、工具统计、Worker 结果摘要已通过 context_ticket / blackboard 传递，
        不需要从消息历史中推断。
        """
        result: list[BaseMessage] = []
        latest_ticket_idx = -1

        # 找到最新的 context_ticket 索引
        for i, msg in enumerate(messages):
            if isinstance(msg, HumanMessage) and msg.name == "context_ticket":
                latest_ticket_idx = i

        for i, msg in enumerate(messages):
            if not isinstance(msg, BaseMessage):
                logger.warning(f"[Supervisor] Skipping non-BaseMessage at index {i}: {type(msg).__name__}")
                continue
            if isinstance(msg, SystemMessage):
                result.append(msg)
            elif isinstance(msg, HumanMessage):
                if msg.name == "context_ticket":
                    if i == latest_ticket_idx:
                        result.append(msg)
                else:
                    result.append(msg)
            elif isinstance(msg, AIMessage):
                if not msg.tool_calls:
                    # 保留总结性 AIMessage（Supervisor 自己的思考、Worker 的最终报告）
                    result.append(msg)
                # 丢弃所有带 tool_calls 的 AIMessage（Worker 的工具调用请求）
            elif isinstance(msg, ToolMessage):
                # 丢弃所有 ToolMessage（Worker 的工具执行结果）
                pass

        dropped = len(messages) - len(result)
        if dropped > 0:
            logger.info(
                f"[Supervisor] Messages filtered: {len(messages)} → {len(result)} "
                f"(dropped={dropped} tool/exec messages)"
            )
        return result

    async def prepare_state(self, state: AgentState, config: RunnableConfig) -> StateUpdate | None:
        """Pre-computation: Check for subtask completion and worker outcome."""
        # NOTE: Token-driven trimming is handled by ContextTrimmer in engine.run_node().
        # Here we apply semantic filtering: Supervisor doesn't need to see Worker's
        # detailed tool-call chains, only high-level mission context and summaries.

        # ─────────────────────────────────────────────────────────────────────
        # Priority 0: Drain queued signal queue.
        # When the Supervisor emitted multiple route_to calls in one turn, the
        # first was dispatched immediately; the rest were serialised into
        # blackboard.pending_signals. Here we drain the queue one entry per
        # Supervisor invocation, bypassing the LLM entirely.
        # ─────────────────────────────────────────────────────────────────────
        blackboard = state.blackboard
        if blackboard and getattr(blackboard, "pending_signals", None):
            import app.core.engine.signals.schemas as schemas
            from app.core.engine.signals.dispatcher import SignalDispatcher

            next_sig_dict = blackboard.pending_signals[0]
            remaining = blackboard.pending_signals[1:]

            try:
                sig_type = next_sig_dict.pop("_type", "RouteToSignal")
                SignalClass = getattr(schemas, sig_type, schemas.RouteToSignal)
                signal = SignalClass.model_validate(next_sig_dict)
                
                dispatch_result = await SignalDispatcher.dispatch(state, signal, config)
                if dispatch_result is not None:
                    bb_update = dispatch_result.blackboard or blackboard

                    bb_update.pending_signals = remaining
                    dispatch_result.blackboard = bb_update

                    # Proactive DB Plan Step sync: advance step status on each
                    # signal consume so the DB plan stays in sync with the
                    # actual signal queue progress.
                    await self._sync_db_plan_step_on_signal_consume(state, config)

                    logger.info(
                        f"[Supervisor] 🚦 Consuming queued signal → {signal.target} "
                        f"| remaining_queue={len(remaining)}"
                    )
                    return dispatch_result
            except Exception as e:
                # If the queued signal is malformed, log and clear the bad entry
                logger.warning(f"[Supervisor] Failed to consume queued signal: {e}. Clearing entry.")
                blackboard.pending_signals = remaining
        # ─────────────────────────────────────────────────────────────────────

        # Filter messages before Supervisor reasoning — this is a "view" operation
        # that does not mutate the global checkpoint state.
        state.messages = self._filter_messages_for_supervisor(list(state.messages))

        # Consume stale routing and plans from previous turns
        from app.core.engine.state.lifecycle import StateLifecycleManager
        StateLifecycleManager.consume_next_node(state)
        StateLifecycleManager.consume_spawn_plan(state)
        StateLifecycleManager.consume_blocked_by_hook(state)

        # Optional: Emit initial status
        await self._emit_status(config, i18n.get("supervisor.status_analyzing"))

        # 1. Aggregate Parallel Results
        blackboard = state.blackboard
        subtask_results = blackboard.subtask_results
        pending_agg = blackboard.pending_aggregation

        if pending_agg and pending_agg.expected_count:
            expected = pending_agg.expected_count
            if len(subtask_results) >= expected:
                logger.info(f"[Supervisor] 🧩 All {expected} subtasks done. Routing to Aggregator.")
                return StateUpdate(next_node=RoutingTarget.AGGREGATOR)

        worker_outcome = StateLifecycleManager.consume_worker_outcome(state)
        if worker_outcome:
            # For "success", "failed", "truncated", or any other semantic outcome:
            # DO NOT intercept with Python logic. Clear the active ticket and 
            # let the Supervisor LLM read the context to decide the next step.
            logger.info(f"[Supervisor] ℹ️ Worker returned '{worker_outcome}'. Delegating review to Supervisor LLM.")
            blackboard.ticket = None

            if worker_outcome in ("truncated", "failed", "error", "incomplete"):
                from langchain_core.messages import SystemMessage
                warning_msg = (
                    f"[SYSTEM ALERT] The previous Worker execution was {worker_outcome.upper()}.\n"
                    "If TRUNCATED: The worker hit its step limit before finishing. You MUST review the progress and issue a new `route_to` ticket to continue the work.\n"
                    "If FAILED/ERROR/INCOMPLETE: Review the last tool errors and decide whether to retry or formulate a new plan.\n"
                    "DO NOT return an empty response. You must take explicit action."
                )
                state.messages.append(SystemMessage(content=warning_msg))

        return None

    async def build_prompt_pair(self, state: AgentState, config: RunnableConfig) -> tuple[str, str]:
        """Construct (Static Instructions, Dynamic Context Ticket)."""
        project_id = state.project_id if state.project_id is not None else DEFAULT_PROJECT_ID
        messages = list(state.messages)

        # Build logical context for the prompt builder
        context = await self._build_context(state, config, messages, project_id)

        prompt_builder = SupervisorPromptBuilder(
            project_id=project_id,
            iteration_count=context.iteration_count,
            context=context,
        )
        # Static Prompt (Cacheable)
        static_system_prompt = await prompt_builder.build(config)
        # Dynamic Ticket (Injected via HumanMessage in BaseAgentNode)
        dynamic_context_ticket = await prompt_builder.build_context_ticket(config, session_goal=state.session_goal)

        return static_system_prompt, dynamic_context_ticket

    async def get_tools(self, state: AgentState) -> list[Any]:
        """Load core routing tools."""
        return await tool_manager.get_node_tools("supervisor", state)

    async def _customize_dispatch_result(
        self,
        dispatch_result: StateUpdate,
        original_state: AgentState,
        engine_result: EngineResult,
        config: RunnableConfig,
    ) -> StateUpdate:
        """Inject iteration_count into signal dispatch results."""
        new_iter_count = (original_state.iteration_count or 0) + 1
        if isinstance(dispatch_result, StateUpdate):
            dispatch_result.iteration_count = new_iter_count
        return dispatch_result

    async def _build_fallback_outcome(
        self,
        original_state: AgentState,
        engine_result: EngineResult,
        config: RunnableConfig,
    ) -> StateUpdate:
        """Supervisor-specific protocol checks when no signal is present."""
        new_iter_count = (original_state.iteration_count or 0) + 1
        new_messages = [
            m for m in (engine_result.messages or [])
            if m.name != "context_ticket"
        ]
        blackboard = engine_result.blackboard or original_state.blackboard

        # Check for infrastructure errors
        has_error_msg = any(
            msg.additional_kwargs.get("is_error") for msg in new_messages
        )
        if has_error_msg:
            return StateUpdate(
                messages=new_messages,
                next_node=RoutingTarget.FINISH,
                blackboard=blackboard,
                iteration_count=new_iter_count,
            )

        # Handle "Silent" Protocol Violation - fallback to CHAT if there is content
        ai_content = ""
        last_msg = new_messages[-1] if new_messages else None

        if isinstance(last_msg, AIMessage):
            ai_content = str(last_msg.content).strip()

        if ai_content:
            # Safety: If Supervisor itself was truncated while trying to recover from
            # Worker truncation, route back to WORKER instead of FINISH.
            if (
                last_msg.additional_kwargs.get("is_truncated")
                and getattr(blackboard, "worker_outcome", None) == "truncated"
            ):
                logger.warning(
                    "[Supervisor] LLM output truncated during truncation recovery. "
                    "Routing back to WORKER."
                )
                return StateUpdate(
                    messages=new_messages,
                    next_node=RoutingTarget.WORKER,
                    blackboard=blackboard,
                    iteration_count=new_iter_count,
                )
            # P1 Improvement: Direct response is now allowed. Route to FINISH.
            return StateUpdate(
                messages=new_messages,
                next_node=RoutingTarget.FINISH,
                blackboard=blackboard,
                iteration_count=new_iter_count,
            )

        # Diagnostic: Why are we stopping?
        logger.error(
            f"[Supervisor] 🛑 Stop: No routing signal and no content. "
            f"Last message type: {type(last_msg).__name__ if last_msg else 'None'}. "
            f"Content length: {len(ai_content)}. "
            f"Has tool_calls: {bool(getattr(last_msg, 'tool_calls', []))}. "
            f"Additional Kwargs Keys: {list(last_msg.additional_kwargs.keys()) if hasattr(last_msg, 'additional_kwargs') else 'N/A'}"
        )

        return StateUpdate(
            messages=new_messages,
            next_node=RoutingTarget.FINISH,
            blackboard=blackboard,
            iteration_count=new_iter_count
        )

    async def _sync_db_plan_step_on_signal_consume(
        self, state: AgentState, config: RunnableConfig
    ) -> None:
        """Proactively sync DB PlanStep status when a queued signal is consumed.

        Each time a signal is drained from pending_signals, the *previous*
        Worker run has just completed successfully. This method:
        1. Marks the first ``in_progress`` DB step as ``completed``.
        2. Marks the next ``pending`` DB step as ``in_progress``.

        This keeps the DB plan in lockstep with the signal queue, preventing
        the post-queue DB check from detecting stale ``pending`` steps and
        triggering an infinite routing loop back to Worker.
        """
        try:
            from app.models.planning import Plan as DBPlan, PlanStep as DBPlanStep

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

                # 1. Complete the current in_progress step
                for step in steps:
                    if step.status == "in_progress":
                        step.status = "completed"
                        step.result = "Completed via signal queue dispatch."
                        break

                # 2. Advance: mark next pending step as in_progress
                for step in steps:
                    if step.status in ("pending",):
                        step.status = "in_progress"
                        break

                logger.debug(
                    "[Supervisor] 📋 DB plan step synced on signal consume"
                )

                # Notify frontend plan panel to refresh
                try:
                    from app.core.engine.message.publisher import MessagePublisher
                    publisher = MessagePublisher(thread_id=thread_id)
                    await publisher.publish_custom_event("plan.updated", {"thread_id": thread_id})
                except Exception as e:
                    logger.debug(f"[Supervisor] Failed to publish plan updated event: {e}")
        except Exception as e:
            logger.debug(f"[Supervisor] DB plan step sync skipped: {e}")

    async def _emit_status(self, config: RunnableConfig, status: str):
        """Emit status update via activity_monitor."""
        try:
            from app.core.monitoring.activity import activity_monitor
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            await activity_monitor.update_agent_state(
                thread_id=thread_id,
                mode="PLANNING",
                task_name="Supervisor Decision",
                task_status=status,
            )
        except Exception as e:
            logger.warning(f"[Supervisor] Failed to emit status update: {e}")

    async def _build_context(
        self, state: AgentState, config: RunnableConfig, messages: list, project_id: int
    ) -> "SupervisorContext":
        """Simplified context builder for LLM planning (Phase 1)."""
        # 1. Get Core Routing Tools — re-use get_tools() result to avoid double-loading
        core_tools = await self.get_tools(state)
        last_msg = get_last_human_message(messages)

        # Get blackboard from state for prompt builder
        blackboard = state.blackboard

        return SupervisorContext(
            tools=core_tools,
            iteration_count=(state.iteration_count or 0),
            last_human_msg=last_msg,
            blackboard=blackboard,
            structured_plan=state.structured_plan or state.current_plan,
        )
