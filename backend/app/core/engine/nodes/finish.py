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
from app.core.engine.state.blackboard import AuditMeta
from app.core.events.schema import SessionCompletedData

logger = logging.getLogger(__name__)


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

        ctx = ContextManager.current()
        messages = list(state.messages)
        blackboard = state.blackboard

        # Light-weight context trimming before finish processing.
        # FinishNode does not go through engine.run_node(), so it does not
        # benefit from the standard ContextTrimmer at the entry point.
        # In extremely long sessions, operating on the full un-trimmed history
        # can cause memory spikes and context overflow. We apply a soft trim
        # here (windowing only, no structural repair) to keep the message list
        # bounded while preserving enough history for summary generation.
        if messages:
            from app.core.engine.context_trimmer import ContextTrimmer
            model = config.get("configurable", {}).get("model")
            if not model:
                raise ValueError(
                    "[FinishNode] No model provided in config. "
                    "Please ensure model is passed via config['configurable']['model']."
                )
            trimmer = ContextTrimmer()
            trim_result = trimmer.trim(
                messages=messages,
                model=model,
                node_source="finish",
                stages={"window"},  # Only windowing; preserve message structure
            )
            from app.core.engine.context_trimmer import TrimTrigger
            if trim_result.trigger != TrimTrigger.NONE:
                logger.info(
                    f"[Finish] Soft trim before audit: {trim_result.before_count} -> "
                    f"{trim_result.after_count} msgs, {trim_result.before_tokens} -> "
                    f"{trim_result.after_tokens} tokens"
                )
            messages = trim_result.messages

        effective_thread_id = (
            ctx.thread_id
            or state.thread_id
            or config.get("configurable", {}).get("thread_id")
            or "unknown"
        )

        # ------------------------------------------------------------
        # 0. Early truncation / replan gate
        # If a Worker hit max_steps and requested replanning, bypass
        # auditing and route straight back to Supervisor.
        # ------------------------------------------------------------
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                meta = getattr(msg, "metadata", {}) or {}
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

        is_shadow_mode = (
            blackboard.metadata.shadow_audit
            if blackboard and blackboard.metadata
            else False
        ) or False

        tool_history = getattr(blackboard.metadata, "tool_history", []) or []

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

        # Apply summary for non-comprehensive tiers
        if audit_tier != "comprehensive":
            for i in range(len(messages) - 1, -1, -1):
                m = messages[i]
                if isinstance(m, AIMessage) and m.content:
                    # Create a new message to avoid mutating the original state.messages
                    messages[i] = AIMessage(
                        content=summary,
                        id=getattr(m, "id", None),
                        name=getattr(m, "name", None),
                        metadata=getattr(m, "metadata", None),
                    )
                    break

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
                metadata={
                    "summary": summary,
                    "audit_tier": audit_tier,
                    "final_outcome": final_outcome,
                    "duration_ms": total_duration,
                },
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
            blackboard_dict=blackboard.model_dump() if hasattr(blackboard, "model_dump") else {},
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
        await publish_session_completed(data=event_data)
        logger.info(f"[Finish] 📡 SessionCompletedEvent published for thread {effective_thread_id}")

        # --------------------------------------------------------------
        # 4. Cleanup pollution (defensive: do NOT mutate original state.messages)
        # --------------------------------------------------------------
        messages_to_return = list(messages)
        cleared_count = 0
        for msg in list(state.messages):
            if isinstance(msg, AIMessage) and msg.content:
                content = str(msg.content)
                if "<evoloop_session_audit>" in content and "<evoloop_final_report>" in content:
                    msg_id = getattr(msg, "id", None)
                    if msg_id:
                        messages_to_return.append(RemoveMessage(id=msg_id))
                    else:
                        # The original msg is in state.messages; we must not mutate it.
                        # Instead, append a cleared copy to the return list.
                        cleared_copy = AIMessage(
                            content="",
                            id=None,
                            name=getattr(msg, "name", None),
                            metadata=getattr(msg, "metadata", None),
                        )
                        messages_to_return.append(cleared_copy)
                        cleared_count += 1
                        logger.warning("[Finish] ⚠️ Audit message has no id, cleared copy appended")

        # --------------------------------------------------------------
        # 5. Automatic state pruning (fire-and-forget)
        # --------------------------------------------------------------
        asyncio.create_task(_safe_prune(effective_thread_id))

        return StateUpdate(
            messages=messages_to_return,
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
