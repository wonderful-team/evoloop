"""
FinishNode — Final session node with quality gating and lifecycle events.

All auditing logic lives in AuditService (app.core.engine.services.audit_service).
This module only orchestrates: audit → hook check → event publish → state prune.
"""

import asyncio
import logging
import re
import time

from langchain_core.messages import AIMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig

from app.core.engine.nodes.base import BaseNode
from app.core.engine.routers import RoutingTarget
from app.core.engine.services.audit_service import AuditService, AuditResult
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.blackboard import AuditMeta, AuditInputData, ProgressMetrics, TaskDeliverable, AuditAnomaly
from app.core.engine.context_trimmer import ContextTrimmer, TrimTrigger
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

    async def _sync_plan_progress_from_db(self, state: "AgentState", blackboard, config: "RunnableConfig" = None) -> None:
        """Sync plan_progress from database to blackboard. Always re-sync to get latest state."""
        metadata = blackboard.metadata
        if not metadata:
            logger.info("[Finish] metadata is None, skipping plan_progress sync")
            return

        thread_id = state.thread_id
        if not thread_id and config:
            thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id:
            logger.info("[Finish] thread_id is None, skipping plan_progress sync")
            return

        logger.info(f"[Finish] Starting plan_progress sync for thread={thread_id}")
        try:
            from sqlalchemy import select
            from sqlalchemy.orm import Session
            from app.infrastructure.database.resource_manager import db_resource_manager
            from app.models.planning import Plan as DBPlan
            from app.core.engine.state.blackboard import PlanProgress

            def _sync_query(tid: str):
                engine = db_resource_manager.sync_engine
                logger.info(f"[Finish] sync_engine={engine is not None}")
                if not engine:
                    return None
                with Session(engine) as session:
                    stmt = select(DBPlan).where(DBPlan.thread_id == tid)
                    plan = session.execute(stmt).scalar_one_or_none()
                    steps_count = len(plan.steps) if plan and plan.steps else 0
                    logger.info(f"[Finish] DB plan found={plan is not None}, steps={steps_count}")
                    if plan and plan.steps:
                        total_steps = len(plan.steps)
                        completed_steps = sum(1 for s in plan.steps if s.status == "completed")
                        return {"total": total_steps, "completed": completed_steps, "plan_id": plan.id}
                    return None

            result = await asyncio.to_thread(_sync_query, thread_id)
            logger.info(f"[Finish] _sync_query result={result is not None}")
            if result:
                metadata.plan_progress = PlanProgress(
                    total_steps=result["total"],
                    completed_steps=result["completed"],
                    plan_id=result["plan_id"],
                )
                logger.info(
                    f"[Finish] Synced plan_progress from DB: {result['completed']}/{result['total']} steps"
                )
            else:
                logger.info("[Finish] No plan found in DB for sync")
        except Exception as e:
            logger.warning(f"[Finish] Failed to sync plan_progress from DB: {e}")

    async def _prepare_audit_input(self, state: "AgentState", blackboard) -> None:
        """Build structured AuditInputData from blackboard state for efficient comprehensive audit.

        This replaces the need for AuditService to scan the full message history (~18K tokens)
        with a compact structured summary (~500 tokens).
        """
        metadata = blackboard.metadata
        if not metadata:
            return

        # If audit_input_data already exists and is fresh, skip rebuild
        if metadata.audit_input_data and metadata.audit_input_data.deliverables:
            return

        # Build tool stats from tool_history
        tool_stats: dict[str, int] = {}
        for sig in metadata.tool_history or []:
            tool_name = sig.split(":")[0] if ":" in sig else sig
            tool_stats[tool_name] = tool_stats.get(tool_name, 0) + 1

        # Build plan summary from blackboard
        plan_progress = metadata.plan_progress
        plan_summary = {}
        if plan_progress:
            plan_summary = {
                "total": plan_progress.total_steps,
                "completed": plan_progress.completed_steps,
                "remaining": max(0, plan_progress.total_steps - plan_progress.completed_steps),
            }

        # Deliverables: use whatever upstream nodes have already recorded.
        # We do NOT query WikiPage, file system, or any other business table here.
        deliverables: list[TaskDeliverable] = (
            list(metadata.audit_input_data.deliverables)
            if metadata.audit_input_data else []
        )
        write_calls = sum(c for t, c in tool_stats.items() if t.startswith("write_"))

        # Detect anomalies from state
        anomalies: list[AuditAnomaly] = list(metadata.audit_anomalies or [])
        msg_count = len(state.messages or [])
        if msg_count > 100:
            anomalies.append(AuditAnomaly(
                anomaly_type="context_overload",
                severity="warn",
                description=f"Message count ({msg_count}) exceeds 100 — possible context saturation",
                suggested_action="Consider truncating history or using semantic summarization",
            ))

        if msg_count > 80:
            anomalies.append(AuditAnomaly(
                anomaly_type="single_turn_saturation",
                severity="info",
                description=f"High message count ({msg_count}) — may indicate single-turn saturation",
                suggested_action="Consider multi-turn execution with heartbeat protocol",
            ))

        # Generic plan-completion anomalies (no business-table queries)
        issues_encountered: list[str] = []
        
        effective_completed = plan_progress.completed_steps if plan_progress else 0
        effective_total = plan_progress.total_steps if plan_progress else 0
        
        # Phase 2: If no DB plan steps, use subtask results as progress proxy
        subtask_results = blackboard.subtask_results
        pending_agg = blackboard.pending_aggregation
        if effective_total == 0 and pending_agg and pending_agg.expected_count:
            effective_total = pending_agg.expected_count
            effective_completed = len(subtask_results)
            logger.info(f"[Finish] Using subtask progress as proxy: {effective_completed}/{effective_total}")

        if effective_total > 0:
            remaining = effective_total - effective_completed
            if remaining > 0:
                issues_encountered.append(
                    f"Plan incomplete: {remaining}/{effective_total} steps pending"
                )
                anomalies.append(AuditAnomaly(
                    anomaly_type="incomplete_plan",
                    severity="warn",
                    description=f"Plan has {remaining} of {effective_total} steps still pending",
                    suggested_action="Route back to Supervisor to continue execution",
                ))
            if effective_completed == 0:
                anomalies.append(AuditAnomaly(
                    anomaly_type="zero_progress",
                    severity="warn",
                    description="No plan steps or subtasks were completed during this session",
                    suggested_action="Investigate why Worker made no progress",
                ))

        # Build progress metrics
        progress = ProgressMetrics(
            total_steps=effective_total,
            completed_steps=effective_completed,
            total_deliverables=len(deliverables),
            completed_deliverables=len(deliverables),
            key_findings=[
                f"Plan/Subtasks: {effective_completed}/{effective_total} steps",
                f"Write tool calls: {write_calls}",
                f"Deliverables recorded by upstream: {len(deliverables)}",
            ],
            issues_encountered=issues_encountered,
        )

        audit_input = AuditInputData(
            original_goal=state.session_goal or "",
            plan_summary=plan_summary,
            progress=progress,
            deliverables=deliverables,
            tool_stats=tool_stats,
            anomalies=anomalies,
            key_messages_digest="",
        )

        metadata.audit_input_data = audit_input
        metadata.audit_anomalies = anomalies
        logger.info(
            f"[Finish] 📊 Prepared structured audit input: "
            f"{plan_summary.get('completed', 0)}/{plan_summary.get('total', 0)} steps, "
            f"{len(deliverables)} deliverables, "
            f"{len(anomalies)} anomalies"
        )

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
            blackboard=state.blackboard,
        )

    async def _run(self, state: "AgentState", config: "RunnableConfig") -> "StateUpdate":
        start_time = time.time()

        # Lazy imports to avoid circular deps at module load
        from app.core.context.manager import ContextManager
        from app.core.engine.hooks import HookContext, HookEvent, hook_system
        from app.core.engine.hooks.schemas import HookMetadata

        ctx = ContextManager.current()
        messages = list(state.messages)
        blackboard = state.blackboard

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
                        user_id=config.get("configurable", {}).get("user_id"),
                        compact_trigger=trim_result.trigger.name.lower(),
                    )
                )

                logger.info(
                    f"[Finish] Soft trim before audit: {trim_result.before_count} -> "
                    f"{trim_result.after_count} msgs, {trim_result.before_tokens} -> "
                    f"{trim_result.after_tokens} tokens"
                )
            messages = trim_result.messages

        # ------------------------------------------------------------
        # 0. Early truncation / replan gate
        # If a Worker hit max_steps and requested replanning, bypass
        # auditing and route straight back to Supervisor.
        # ------------------------------------------------------------
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                meta = msg.additional_kwargs
                if meta.get("is_truncated") and meta.get("requires_replan"):
                    logger.warning(
                        f"[Finish] 🔄 Worker was truncated (max_steps={meta.get('max_steps')}). "
                        "Routing back to Supervisor for replanning."
                    )
                    blackboard.worker_outcome = "failed"
                    return StateUpdate(
                        messages=messages,
                        next_node=RoutingTarget.SUPERVISOR,
                        blackboard=blackboard,
                    )

        is_shadow_mode = blackboard.metadata.shadow_audit or False
        tool_history = blackboard.metadata.tool_history

        # Phase 1: Sync plan progress + prepare audit input before calling AuditService
        await self._sync_plan_progress_from_db(state, blackboard, config)
        await self._prepare_audit_input(state, blackboard)

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
        audit_tier = audit_result.tier
        audit_meta = AuditMeta(**audit_result.meta)

        # Comprehensive audit already updated messages/blackboard
        if audit_tier == "comprehensive":
            if audit_result.messages:
                messages = list(audit_result.messages)
            if audit_result.blackboard:
                blackboard = audit_result.blackboard
            summary = audit_result.summary
            audit_meta = AuditMeta(
                tier="comprehensive",
                duration_ms=(time.time() - start_time) * 1000,
            )

        # Extract outcome tag
        full_text = "".join([str(m.content) for m in messages if isinstance(m, AIMessage)])
        outcome_match = re.search(
            r"<evoloop_audit_outcome>(.*?)</evoloop_audit_outcome>",
            full_text,
            re.IGNORECASE | re.DOTALL,
        )
        final_outcome = ""
        if outcome_match:
            final_outcome = outcome_match.group(1).strip()
            blackboard.metadata.final_outcome = final_outcome
            logger.info(f"[Finish] 🎯 Outcome: {final_outcome}")

        # NEW: Enforce audit verdict — INCOMPLETE routes back to Supervisor
        if final_outcome.upper() == "INCOMPLETE":
            logger.warning(f"[Finish] 🔄 Audit verdict: INCOMPLETE. Routing back to Supervisor.")
            blackboard.worker_outcome = "incomplete"
            return StateUpdate(
                messages=messages,
                next_node=RoutingTarget.SUPERVISOR,
                blackboard=blackboard,
            )

        # Apply summary ONLY for comprehensive tiers to avoid technical log pollution
        if audit_tier == "comprehensive":
            for i in range(len(messages) - 1, -1, -1):
                m = messages[i]
                if isinstance(m, AIMessage) and m.content:
                    messages[i] = AIMessage(
                        content=summary,
                        id=m.id,
                        name=m.name,
                        metadata=m.additional_kwargs,
                    )
                    break
        else:
            logger.debug(f"[Finish] Silent audit (tier={audit_tier}) - not updating message content.")

        # Persist audit metadata
        blackboard.metadata.audit_tier = audit_tier
        blackboard.metadata.audit_meta = audit_meta
        blackboard.summary = summary

        total_duration = (time.time() - start_time) * 1000

        # --------------------------------------------------------------
        # 2. STOP hook (blocking quality gate)
        # --------------------------------------------------------------
        try:
            stop_ctx = HookContext(
                thread_id=effective_thread_id,
                user_id=ctx.user_id,
                project_id=ctx.project_id,
                messages=messages,
                blackboard=blackboard,
                metadata=HookMetadata(
                    summary=summary,
                    audit_tier=audit_tier,
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
                blackboard.metadata.blocked_by_hook = True
                blackboard.worker_outcome = "failed"
                return StateUpdate(
                    messages=messages + [block_msg],
                    next_node=RoutingTarget.SUPERVISOR,
                    blackboard=blackboard,
                )
        except Exception as e:
            logger.exception(f"[Finish] Stop hook failed: {e}")

        # --------------------------------------------------------------
        # 3. Publish completion event
        # --------------------------------------------------------------
        logger.info(f"[Finish] ✅ {audit_tier.upper()} audit complete: {total_duration:.0f}ms. Finalizing session...")

        metadata = config.get("metadata", {})
        run_id = config.get("configurable", {}).get("run_id")

        event_data = SessionCompletedData(
            thread_id=effective_thread_id,
            run_id=run_id,
            project_id=ctx.project_id,
            user_id=ctx.user_id,
            messages=messages,
            blackboard_dict=blackboard.model_dump(),
            summary=summary,
            outcome=final_outcome,
            audit_tier=audit_tier,
            duration_ms=total_duration,
            model=ctx.active_model,
            original_skill_id=metadata.get("original_skill_id"),
            ticket_topic=blackboard.ticket.topic if blackboard.ticket else None,
            ticket_reason=blackboard.ticket.reason if blackboard.ticket else None,
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
        blackboard.subtask_results = []
        blackboard.spawn_plan = None
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
            blackboard=blackboard,
        )


# ---------------------------------------------------------------------------
# Safe pruning wrapper — prevents exception leakage
# ---------------------------------------------------------------------------

async def _safe_prune(thread_id: str) -> None:
    """Wrap auto_prune_on_completion so exceptions never leak."""
    try:
        from app.core.engine.checkpoint.pruner import auto_prune_on_completion
        await auto_prune_on_completion(thread_id)
    except Exception:
        logger.exception(f"[Finish] auto_prune_on_completion failed for thread {thread_id}")
