"""
FinishNode — Final session node with quality gating and lifecycle events.

All auditing logic lives in AuditService (app.core.engine.services.audit_service).
This module only orchestrates: audit → hook check → event publish → state prune.
"""

import asyncio
import logging
import time

from langchain_core.messages import AIMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.engine.checkpoint.pruner import auto_prune_on_completion
from app.core.engine.context_trimmer import ContextTrimmer, TrimTrigger
from app.core.engine.nodes.base import BaseNode
from app.core.engine.routers import RoutingTarget
from app.core.engine.services.audit_service import AuditResult, AuditService
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.sub_schemas import (
    AuditAnomaly,
    AuditInputData,
    ProgressMetrics,
)
from app.core.events.schemas import SessionCompletedData

logger = logging.getLogger(__name__)

# Module-level singleton — avoids re-instantiation on every FinishNode call
_trimmer = ContextTrimmer()


class FinishNode(BaseNode):
    """Final node: quality audit, hooks, and session finalization."""

    def __init__(self, audit_service: AuditService | None = None):
        super().__init__(node_name="Finish")
        self._audit_service = audit_service

    async def __call__(self, state: "AgentState", config: "RunnableConfig") -> "StateUpdate":
        from app.core.engine.state import ensure_state
        state = ensure_state(state)
        try:
            return await self._run(state, config)
        except Exception as e:
            logger.exception(f"[Finish] Audit or finalization failed: {e}")
            return await self.handle_error(state, e, config=config)

    async def _prepare_audit_input(self, state: "AgentState") -> None:
        # Build structured progress from memory (no DB required)
        plan_progress = state.plan_progress
        effective_completed = plan_progress.completed_steps if plan_progress else 0
        effective_total = plan_progress.total_steps if plan_progress else 0

        # Fallback to subtasks if no formal plan
        subtask_results = state.subtask_results
        pending_agg = state.pending_aggregation
        if effective_total == 0 and pending_agg and pending_agg.expected_count:
            effective_total = pending_agg.expected_count
            effective_completed = len(subtask_results)

        # Estimate deliverables from tool history (avoids DB hit)
        tool_history = state.tool_history or []
        created_count = sum(1 for t in tool_history if "write_" in t or "edit_" in t or "create_" in t)

        progress = ProgressMetrics(
            total_steps=effective_total,
            completed_steps=effective_completed,
            total_deliverables=created_count,
            completed_deliverables=created_count,
            key_findings=[f"Cognitive Progress: {effective_completed}/{effective_total} steps"],
            issues_encountered=[],
        )

        anomalies = []
        if effective_total > 0 and effective_completed < effective_total:
            anomalies.append(AuditAnomaly(
                anomaly_type="incomplete_plan",
                severity="warn",
                description=f"Plan incomplete: {effective_completed}/{effective_total}",
                suggested_action="Route back to Supervisor",
            ))

        audit_input = AuditInputData(
            original_goal=state.session_goal or "",
            plan_summary={"total": effective_total, "completed": effective_completed},
            progress=progress,
            deliverables=[],
            tool_stats={},
            anomalies=anomalies,
            key_messages_digest="",
        )
        state.audit_input_data = audit_input
        state.audit_anomalies = anomalies

    async def handle_error(self, state: "AgentState", error: Exception, config: "RunnableConfig" = None) -> "StateUpdate":
        """Finish-specific error handling: route to END, not SUPERVISOR."""
        from langchain_core.messages import AIMessage
        error_msg = AIMessage(
            content=f"Session finalization failed: {error}",
            metadata={"is_error": True, "error_type": "finish_failure"},
        )
        return StateUpdate(
            messages=list(state.messages) + [error_msg],
            next_node=RoutingTarget.END,
        )

    async def _run(self, state: "AgentState", config: "RunnableConfig") -> "StateUpdate":
        start_time = time.time()

        # Lazy imports to avoid circular deps at module load
        from app.core.context.manager import ContextManager
        from app.core.engine.hooks import HookContext, HookEvent, hook_system
        from app.core.engine.hooks.schemas import HookMetadata

        ctx = ContextManager.current()
        messages = list(state.messages)

        effective_thread_id = (
            ctx.thread_id
            or state.thread_id
            or config.get("configurable", {}).get("thread_id")
            or "unknown"
        )

        # Light-weight context trimming before finish processing.
        # FinishNode does not go through engine.run_node(), so it does not
        # benefit from the standard ContextTrimmer at the entry point.
        # In extremely long sessions, operating on the full un-trimmed history
        # can cause memory spikes and context overflow. We apply a soft trim
        # here (windowing only, no structural repair) to keep the message list
        # bounded while preserving enough history for summary generation.
        if messages:
            model = config.get("configurable", {}).get("model")
            if not model:
                raise ValueError(
                    "[FinishNode] No model provided in config. "
                    "Please ensure model is passed via config['configurable']['model']."
                )
            trim_result = _trimmer.trim(
                messages=messages,
                model=model,
                node_source="finish",
                stages={"window"},  # Only windowing; preserve message structure
            )
            if trim_result.trigger != TrimTrigger.NONE:
                # Trigger PRE_COMPACT hook BEFORE applying the trim to save state
                from app.core.engine.hooks import HookContext, HookEvent, hook_system
                await hook_system.trigger(
                    HookEvent.PRE_COMPACT,
                    HookContext(
                        thread_id=effective_thread_id,
                        run_id=config.get("configurable", {}).get("run_id"),
                        messages=messages,
                        project_id=config.get("configurable", {}).get("project_id"),
                        member_id=config.get("configurable", {}).get("member_id"),
                        compact_trigger=trim_result.trigger.name.lower(),
                    )
                )

                logger.info(
                    f"[Finish] Soft trim before audit: {trim_result.before_count} -> "
                    f"{trim_result.after_count} msgs, {trim_result.before_tokens} -> "
                    f"{trim_result.after_tokens} tokens"
                )
            messages = trim_result.messages

        iteration_count = (state.iteration_count or 0)
        max_steps = settings.SUPERVISOR_AGENT_MAX_STEPS
        if state.max_supervisor_steps:
            max_steps = state.max_supervisor_steps

        is_shadow_mode = state.shadow_audit or False
        tool_history = state.tool_history or []

        # Sync plan progress + prepare audit input before calling AuditService
        await self._prepare_audit_input(state)

        # --------------------------------------------------------------
        # 1. Audit
        # --------------------------------------------------------------
        service = self._audit_service or AuditService()
        audit_result: AuditResult = await service.execute(
            state=state,
            config=config,
            tool_history=tool_history,
            is_shadow_mode=is_shadow_mode,
        )

        summary = audit_result.summary

        final_outcome = audit_result.meta.get("outcome", "")

        # Enforce audit verdict — INCOMPLETE routes back to Supervisor
        if final_outcome.upper() == "INCOMPLETE":
            if iteration_count < max_steps:
                logger.warning("[Finish] 🔄 Audit verdict: INCOMPLETE. Routing back to Supervisor.")
                return StateUpdate(
                    messages=messages,
                    next_node=RoutingTarget.SUPERVISOR,
                    worker_outcome="incomplete",
                    final_outcome=final_outcome,
                )
            else:
                logger.warning(f"[Finish] ⚠️ Audit verdict: INCOMPLETE, but iteration limit ({max_steps}) reached. Forcing completion.")

        # Persist audit metadata
        state.audit_tier = "unified"
        state.summary = summary

        total_duration = (time.time() - start_time) * 1000

        # --------------------------------------------------------------
        # 2. STOP hook (blocking quality gate)
        # --------------------------------------------------------------
        try:
            stop_ctx = HookContext(
                thread_id=effective_thread_id,
                member_id=ctx.member_id,
                project_id=ctx.project_id,
                messages=messages,
                state=state,
                metadata=HookMetadata(
                    summary=summary,
                    audit_tier="unified",
                    final_outcome=final_outcome,
                    duration_ms=total_duration,
                ),
            )
            stop_result = await hook_system.trigger(HookEvent.STOP, stop_ctx, blocking=True)
            if stop_result.block:
                logger.warning(f"[Finish] 🚫 Stop hook blocked completion: {stop_result.message}")
                block_msg = AIMessage(
                    content=f"\n\n[Quality Gate Blocked] {stop_result.message}\nPlease address the issues before completing."
                )
                state.blocked_by_hook = True
                return StateUpdate(
                    messages=messages + [block_msg],
                    next_node=RoutingTarget.SUPERVISOR,
                    worker_outcome="failed",
                    blocked_by_hook=True,
                )
        except Exception as e:
            logger.exception(f"[Finish] Stop hook failed: {e}")

        # --------------------------------------------------------------
        # 3. Publish completion event
        # --------------------------------------------------------------
        logger.info(f"[Finish] ✅ Audit complete: {total_duration:.0f}ms. Finalizing session...")

        metadata = config.get("metadata", {})
        run_id = config.get("configurable", {}).get("run_id")

        # Construct legacy blackboard_dict for event publication
        metadata_fields = {
            "tool_history": state.tool_history,
            "pending_approvals": [x.model_dump() if hasattr(x, "model_dump") else x for x in (state.pending_approvals or [])],
            "audit_anomalies": [x.model_dump() if hasattr(x, "model_dump") else x for x in (state.audit_anomalies or [])],
            "tool_memory": state.tool_memory,
            "final_outcome": state.final_outcome,
            "shadow_audit": state.shadow_audit,
            "termination_outcome": state.termination_outcome,
            "last_aggregation_result": state.last_aggregation_result,
            "audit_tier": state.audit_tier,
            "audit_meta": state.audit_meta.model_dump() if hasattr(state.audit_meta, "model_dump") and state.audit_meta else state.audit_meta,
            "blocked_by_hook": state.blocked_by_hook,
            "plan_progress": state.plan_progress.model_dump() if hasattr(state.plan_progress, "model_dump") and state.plan_progress else state.plan_progress,
            "max_supervisor_steps": state.max_supervisor_steps,
            "audit_input_data": state.audit_input_data.model_dump() if hasattr(state.audit_input_data, "model_dump") and state.audit_input_data else state.audit_input_data,
            "force_comprehensive_audit": state.force_comprehensive_audit,
        }
        metadata_clean = {k: v for k, v in metadata_fields.items() if v is not None}

        blackboard_dict = {
            "ticket": state.ticket.model_dump() if hasattr(state.ticket, "model_dump") and state.ticket else state.ticket,
            "subtask_results": state.subtask_results,
            "visited_nodes": state.visited_nodes,
            "verification": state.verification.model_dump() if hasattr(state.verification, "model_dump") and state.verification else state.verification,
            "metadata": metadata_clean,
        }

        event_data = SessionCompletedData(
            thread_id=effective_thread_id,
            run_id=run_id,
            project_id=ctx.project_id,
            member_id=ctx.member_id,
            messages=messages,
            blackboard_dict=blackboard_dict,
            summary=summary,
            outcome=final_outcome,
            audit_tier="unified",
            duration_ms=total_duration,
            turn_summary_message_id=None,
            model=ctx.active_model,
            original_skill_id=metadata.get("original_skill_id"),
            ticket_topic=state.ticket.topic if state.ticket else None,
            ticket_reason=state.ticket.reason if state.ticket else None,
        )

        from app.core.events.publishers import publish_session_completed
        if not metadata.get("skip_persistence"):
            logger.info(f"[Finish] 📡 Publishing SessionCompletedEvent for thread {effective_thread_id}...")
            await publish_session_completed(data=event_data)

        # --------------------------------------------------------------
        # 4. Cleanup pollution (defensive: do NOT mutate original state.messages)
        # --------------------------------------------------------------
        messages_to_return = list(messages)
        cleared_count = 0
        for msg in list(state.messages):
            if isinstance(msg, AIMessage) and msg.content:
                content = str(msg.content)
                if "<evoloop_session_audit>" in content and "<evoloop_final_report>" in content:
                    if msg.id:
                        messages_to_return.append(RemoveMessage(id=msg.id))
                    else:
                        # The original msg is in state.messages; we must not mutate it.
                        # Instead, append a cleared copy to the return list.
                        cleared_copy = AIMessage(
                            content="",
                            id=None,
                            name=msg.name,
                            metadata=msg.additional_kwargs,
                        )
                        messages_to_return.append(cleared_copy)
                        cleared_count += 1
                        logger.warning("[Finish] ⚠️ Audit message has no id, cleared copy appended")

        # --------------------------------------------------------------
        # 5. Blackboard Pruning: Clear transient subtask data to prevent bloat
        # --------------------------------------------------------------
        state.subtask_results = []
        state.spawn_plan = None
        logger.debug(f"[Finish] Blackboard pruned for thread {effective_thread_id}")

        # --------------------------------------------------------------
        # 6. Automatic state pruning (fire-and-forget)
        # --------------------------------------------------------------
        asyncio.create_task(_safe_prune(effective_thread_id))

        # LangGraph optimization: only return messages that were ADDED or MODIFIED during this node.
        # Since we modified the original messages list and potentially added RemoveMessage markers,
        # we return the delta.
        # NOTE: Returning the full list 'messages_to_return' causes duplication in LangGraph
        # because it appends everything to the state.

        # We only return messages that are NOT already in the original state.messages list
        # OR if they are RemoveMessage / placeholder messages.
        existing_ids = {m.id for m in state.messages if m.id}
        delta_messages = [
            m for m in messages_to_return
            if not m.id or m.id not in existing_ids or isinstance(m, RemoveMessage)
        ]

        return StateUpdate(
            messages=delta_messages,
            next_node=RoutingTarget.END,
            subtask_results=[],
            spawn_plan=None,
            final_outcome=final_outcome,
            audit_tier="unified",
            summary=summary,
        )


# ---------------------------------------------------------------------------
# Safe pruning wrapper — prevents exception leakage
# ---------------------------------------------------------------------------

async def _safe_prune(thread_id: str) -> None:
    """Wrap auto_prune_on_completion so exceptions never leak."""
    try:
        await auto_prune_on_completion(thread_id)
    except Exception:
        logger.exception(f"[Finish] auto_prune_on_completion failed for thread {thread_id}")
