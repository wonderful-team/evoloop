"""
FinishNode — Final session node with quality gating and lifecycle events.
"""

import logging
import re
import time

from app.core.config import settings
from app.core.engine.context_trimmer import ContextTrimmer, TrimTrigger
from app.core.engine.message.native_classes import SystemMessage
from app.core.engine.nodes.base import BaseNode
from app.core.engine.routers import RoutingTarget
from app.core.engine.services.audit_service import AuditResult, AuditService
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.sub_schemas import AuditAnomaly, AuditInputData, ProgressMetrics
from app.core.events.schemas import SessionCompletedData
from app.infrastructure.database import session_scope
from app.models import AgentActivity
from app.utils.template import render_template
from app.utils.time import elapsed_ms

logger = logging.getLogger(__name__)

_trimmer = ContextTrimmer()


class FinishNode(BaseNode):
    """Final node: quality audit, hooks, and session finalization."""

    def __init__(self, audit_service: AuditService | None = None):
        super().__init__(node_name="Finish")
        self._audit_service = audit_service

    async def __call__(self, state: "AgentState", config: dict) -> "StateUpdate":
        from app.core.engine.state import ensure_state

        state = ensure_state(state)
        try:
            return await self._run(state, config)
        except (ValueError, RuntimeError, OSError) as e:
            logger.exception(f"[Finish] Audit or finalization failed: {e}")
            return await self.handle_error(state, e, config=config)

    async def _prepare_audit_input(self, state: "AgentState") -> None:
        from collections import Counter

        plan_progress = state.plan_progress
        effective_completed = plan_progress.completed_steps if plan_progress else 0
        effective_total = plan_progress.total_steps if plan_progress else 0

        tool_history = state.tool_history or []
        created_count = sum(
            1 for t in tool_history if "write_" in t or "edit_" in t or "create_" in t
        )

        # Tool usage digest so the audit can see what was actually attempted.
        tool_counts = Counter(t.split(":")[0] for t in tool_history)
        tool_stats = dict(tool_counts.most_common(10))

        # Preserve the most recent worker final report / system note in the audit input.
        key_digest = ""
        for msg in reversed(state.messages):
            if msg.role == "assistant" and not getattr(msg, "tool_calls", None):
                text = str(getattr(msg, "content", "") or "").strip()
                if len(text) > 30:
                    key_digest = text[:600]
                    break
        if not key_digest:
            for msg in reversed(state.messages):
                if msg.role == "system":
                    text = str(getattr(msg, "content", "") or "").strip()
                    if len(text) > 30:
                        key_digest = text[:600]
                        break

        verification_status = ""
        if state.verification and state.verification.status:
            verification_status = state.verification.status

        key_findings = [
            f"Cognitive Progress: {effective_completed}/{effective_total} steps"
        ]
        if key_digest:
            key_findings.append(f"Final worker report (excerpt): {key_digest[:200]}")
        if verification_status:
            key_findings.append(f"Verification status: {verification_status}")

        progress = ProgressMetrics(
            total_steps=effective_total,
            completed_steps=effective_completed,
            total_deliverables=created_count,
            completed_deliverables=created_count,
            key_findings=key_findings,
            issues_encountered=[],
        )

        anomalies = []
        if effective_total > 0 and effective_completed < effective_total:
            anomalies.append(
                AuditAnomaly(
                    anomaly_type="incomplete_plan",
                    severity="warn",
                    description=f"Plan incomplete: {effective_completed}/{effective_total}",
                    suggested_action="Route back to Supervisor",
                )
            )
        # If the worker already concluded that verification is impossible due to
        # environment limitations, do not flag it as actionable incompleteness.
        if state.shared_context and state.shared_context.get("verification_impossible"):
            anomalies = [
                a for a in anomalies
                if a.anomaly_type != "incomplete_plan"
            ]
            anomalies.append(
                AuditAnomaly(
                    anomaly_type="verification_impossible",
                    severity="info",
                    description="Worker reported that verification is impossible in the current environment.",
                    suggested_action="Accept the worker's final report and finish.",
                )
            )

        audit_input = AuditInputData(
            original_goal=state.session_goal or "",
            plan_summary={"total": effective_total, "completed": effective_completed},
            progress=progress,
            deliverables=[],
            tool_stats=tool_stats,
            anomalies=anomalies,
            key_messages_digest=key_digest,
        )
        state.audit_input_data = audit_input
        state.audit_anomalies = anomalies

    async def handle_error(
        self, state: "AgentState", error: Exception, config: dict = None
    ) -> "StateUpdate":
        from app.core.engine.message.native_classes import AIMessage

        error_msg = AIMessage(
            content=f"Session finalization failed: {error}",
            additional_kwargs={"is_error": True, "error_type": "finish_failure"},
        )
        return StateUpdate(
            messages=state.messages + [error_msg],
            next_node=RoutingTarget.END,
        )

    async def _update_agent_activity(
        self,
        thread_id: str,
        summary: str | None,
        final_outcome: str,
    ) -> None:
        """Persist the audit summary and outcome to AgentActivity."""
        try:
            async with session_scope() as session:
                activity = await session.get(AgentActivity, thread_id)
                if activity is None:
                    logger.debug(
                        f"[Finish] No AgentActivity record for {thread_id}; skipping activity update."
                    )
                    return
                activity.summary = summary
                activity.final_outcome = final_outcome
        except Exception as e:
            logger.warning(
                f"[Finish] Failed to update AgentActivity for {thread_id}: {e}",
                exc_info=True,
            )

    async def _run(self, state: "AgentState", config: dict) -> "StateUpdate":
        start_time = time.time()

        from app.core.context.manager import ContextManager
        from app.core.engine.hooks import HookContext, HookEvent, hook_system
        from app.core.engine.hooks.schemas import HookMetadata

        ctx = ContextManager.current()
        messages = state.messages

        effective_thread_id = (
            ctx.thread_id
            or state.thread_id
            or config.get("configurable", {}).get("thread_id")
        )

        if messages:
            model = config.get("configurable", {}).get("model")
            trim_result = _trimmer.trim(
                messages=messages,
                model=model,
                node_source="finish",
                stages={"window"},
            )
            if trim_result.trigger != TrimTrigger.NONE:
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
                    ),
                )

                logger.info(
                    f"[Finish] Soft trim before audit: {trim_result.before_count} -> {trim_result.after_count} msgs"
                )
            messages = trim_result.messages

        iteration_count = state.iteration_count or 0
        max_steps = settings.SUPERVISOR_AGENT_MAX_STEPS
        if state.max_supervisor_steps:
            max_steps = state.max_supervisor_steps

        is_shadow_mode = state.shadow_audit or False
        tool_history = state.tool_history or []

        # 审计输入只在真正要审计时构建（needs_audit=false 直接以最终回复收尾，
        # 不必为不执行的审计准备结构化输入）。
        needs_audit = bool(state.ticket and state.ticket.needs_audit)
        if needs_audit:
            await self._prepare_audit_input(state)

        service = self._audit_service or AuditService()
        audit_result: AuditResult = await service.execute(
            state=state,
            config=config,
            tool_history=tool_history,
            is_shadow_mode=is_shadow_mode,
        )

        summary = audit_result.summary
        final_outcome = audit_result.meta.get("outcome", "")
        await self._update_agent_activity(
            thread_id=effective_thread_id,
            summary=summary,
            final_outcome=final_outcome,
        )

        if final_outcome.upper() == "INCOMPLETE":
            retry_count = state.audit_retry_count or 0
            correctable = bool(
                audit_result.meta.get("correctable") or state.audit_correctable
            )
            # Phase E3: correctable=true 且未超重试上限（≤2）→ 机器路由回 Worker
            # 针对性修正（执行层闭环，Supervisor 不介入）。超限升级 Supervisor。
            # 修正指令必须是监察者实际给出的理由；无理由的撤回不构成可执行指令，
            # 不硬编兜底文案，直接升级 Supervisor 决策。
            correction = state.audit_reason or audit_result.meta.get("reason")
            if correctable and correction and retry_count < 2 and iteration_count < max_steps:
                correction_msg = SystemMessage(
                    content=render_template(
                        "core/engine/fragments/auditor_correction.j2",
                        correction=correction,
                    )
                )
                logger.warning(
                    f"[Finish] Verdict: INCOMPLETE + correctable. Routing back to "
                    f"Worker (retry {retry_count + 1}/2)."
                )
                return StateUpdate(
                    messages=messages + [correction_msg],
                    next_node=RoutingTarget.WORKER,
                    worker_outcome="incomplete",
                    final_outcome=final_outcome,
                    audit_retry_count=retry_count + 1,
                )
            if iteration_count < max_steps:
                logger.warning(
                    "[Finish] Verdict: INCOMPLETE. Routing back to Supervisor."
                )
                return StateUpdate(
                    messages=messages,
                    next_node=RoutingTarget.SUPERVISOR,
                    worker_outcome="incomplete",
                    final_outcome=final_outcome,
                )
            else:
                logger.warning(
                    "[Finish] Verdict: INCOMPLETE, iteration limit reached. Forcing completion."
                )

        state.audit_tier = "unified"
        state.summary = summary
        total_duration = elapsed_ms(start_time)

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
            stop_result = await hook_system.trigger(
                HookEvent.STOP, stop_ctx, blocking=True
            )
            if stop_result.block:
                logger.warning(
                    f"[Finish] STOP hook blocked completion: {stop_result.message}"
                )
                from app.core.engine.message.native_classes import AIMessage

                block_msg = AIMessage(
                    content=f"\n\n[Quality Gate Blocked] {stop_result.message}\nPlease address the issues before completing.",
                )
                state.blocked_by_hook = True
                return StateUpdate(
                    messages=messages + [block_msg],
                    next_node=RoutingTarget.SUPERVISOR,
                    worker_outcome="failed",
                    blocked_by_hook=True,
                )
        except (ValueError, RuntimeError, OSError) as e:
            logger.exception(f"[Finish] Stop hook failed: {e}")

        logger.info(
            f"[Finish] Audit complete: {total_duration:.0f}ms. Finalizing session..."
        )

        metadata = config.get("metadata", {})
        run_id = config.get("configurable", {}).get("run_id")

        metadata_clean = state.build_metadata_dict()

        blackboard_dict = {
            "ticket": state.ticket.model_dump() if state.ticket else None,
            "visited_nodes": state.visited_nodes,
            "verification": state.verification.model_dump()
            if state.verification
            else None,
            "metadata": metadata_clean,
        }

        # Clean session audit/finish messages from message history (they are internal quality gates)
        messages_to_return = []
        for msg in messages:
            role = msg.type
            content = msg.content or ""
            is_internal_finish = (
                role == "assistant"
                and content
                and (
                    "<evoloop_session_audit>" in str(content)
                    or "<evoloop_final_report>" in str(content)
                    or "<evoloop_tts_summary>" in str(content)
                )
            )
            if not is_internal_finish:
                messages_to_return.append(msg)

        # Extract tts_summary from the audit LLM response (not from original state messages)
        tts_summary = ""
        for msg in audit_result.messages or []:
            content = msg.content or ""
            if "<evoloop_tts_summary>" in str(content):
                m = re.search(
                    r"<evoloop_tts_summary>(.*?)</evoloop_tts_summary>",
                    str(content),
                    re.DOTALL,
                )
                if m:
                    tts_summary = m.group(1).strip()
                    break

        # Convert native dict messages back to native list of dicts for event schema if needed,
        # but since SessionCompletedData expects standard messages list, we can just pass dict list.
        event_data = SessionCompletedData(
            thread_id=effective_thread_id,
            run_id=run_id,
            project_id=ctx.project_id,
            member_id=ctx.member_id,
            messages=messages_to_return,
            blackboard_dict=blackboard_dict,
            summary=summary,
            tts_summary=tts_summary,
            outcome=final_outcome,
            audit_tier="unified",
            duration_ms=total_duration,
            turn_summary_message_id=None,
            model=ctx.active_model,
            source=metadata.get("source"),
            original_skill_id=metadata.get("original_skill_id"),
            ticket_topic=state.ticket.topic if state.ticket else None,
            ticket_reason=state.ticket.reason if state.ticket else None,
        )

        from app.core.events.publishers import publish_session_completed

        if not metadata.get("skip_persistence"):
            logger.info(
                f"[Finish] Publishing SessionCompletedEvent for thread {effective_thread_id}..."
            )
            await publish_session_completed(data=event_data)

        logger.debug(f"[Finish] Blackboard pruned for thread {effective_thread_id}")

        return StateUpdate(
            messages=messages_to_return,
            next_node=RoutingTarget.END,
            final_outcome=final_outcome,
            audit_tier="unified",
            summary=summary,
        )
