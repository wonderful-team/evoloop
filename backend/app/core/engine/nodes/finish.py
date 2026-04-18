import asyncio
import logging
import re
import time

from langchain_core.messages import AIMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig

from app.constants import DEFAULT_PROJECT_ID
from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.engine import get_default_engine
from app.core.engine.checkpoint.pruner import auto_prune_on_completion
from app.core.engine.prompts.finish import FinishPromptBuilder
from app.core.engine.routers import RoutingTarget
from app.core.engine.state import AgentState, StateUpdate
from app.core.engine.state.blackboard import AuditMeta, BlackboardState, VerificationStatus
from app.core.events import system_bus
from app.core.events.schema import SessionCompletedEvent, SessionCompletedData
from app.core.tools.manager import tool_manager
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


def _extract_tool_usage(messages: list) -> str:
    """Extract a summary of tools used in the session to prove activity."""
    tools_used = set()
    from langchain_core.messages import AIMessage, ToolMessage

    for msg in messages:
        if isinstance(msg, AIMessage):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    if name:
                        tools_used.add(name)
            elif msg.additional_kwargs and "tool_calls" in msg.additional_kwargs:
                for tc in msg.additional_kwargs["tool_calls"]:
                    name = tc.get("function", {}).get("name") if "function" in tc else tc.get("name")
                    if name:
                        tools_used.add(name)
        elif isinstance(msg, ToolMessage) or (hasattr(msg, "tool_call_id") and msg.tool_call_id):
            name = getattr(msg, "name", None)
            if name:
                tools_used.add(name)

    from app.utils import PerceptionsFormatter
    formatted = PerceptionsFormatter.tools_used(tools_used)

    if not formatted or formatted.strip() == "":
        if not tools_used:
            return "No tool actions were recorded in this session."
        return f"Tools utilized: {', '.join(sorted(tools_used))}"

    return formatted


def _extract_final_summary(messages: list) -> str:
    """Extract the last AIMessage text as the reviewer's conclusion."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            content = str(msg.content)

            report_match = re.search(r"<evoloop_final_report>(.*?)</evoloop_final_report>", content, flags=re.DOTALL | re.IGNORECASE)
            if report_match:
                return report_match.group(1).strip()

            content = re.sub(r"<(session_audit|audit_outcome|audit_reason|audit_proof)>.*?</\1>", "", content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r"<[^>]+>", "", content)
            content = re.sub(r"^\s*[^:\n]{1,25}:\s*", "", content, flags=re.MULTILINE)
            content = content.replace("```", "").strip()

            return content[:2000]
    return i18n.get("finish.session_concluded")

# ===== Layered Auditor Classes =====

class AuditDecision:
    """Decision for audit tier selection."""
    def __init__(self, tier: str, reason: str, confidence: float):
        self.tier = tier
        self.reason = reason
        self.confidence = confidence


class LayeredAuditor:
    """
    Three-tier finish auditor with quality preservation.
    """

    READONLY_TOOLS = frozenset({
        'read_file', 'list_directory', 'get_file_info', 'search_files',
        'analyze_image', 'search_web', 'read_url_content',
        'search_history', 'search_skills',
    })

    FILE_WRITE_TOOLS = frozenset({
        'write_file', 'edit_file', 'delete_file', 'move_file', 'create_directory',
    })

    EXECUTION_TOOLS = frozenset({
        'execute_command', 'bash', 'shell', 'python',
    })

    AUTOMATION_TOOLS = frozenset({
        'mobile_control', 'browser_control', 'desktop_control',
        'open_app', 'click_at', 'type_text', 'press_key',
    })

    ERROR_PATTERNS = [
        r'\[ERROR:', r'^Error:', r'Exception:', r'Traceback',
        r'Failed to', r'Permission denied', r'File not found',
    ]

    def classify_tier(self, tool_history: list, messages: list, blackboard: "BlackboardState", state: AgentState) -> AuditDecision:
        """Classify which audit tier is appropriate."""
        used_tools = set()
        for sig in tool_history:
            tool_name = sig.split(':')[0] if ':' in sig else sig
            used_tools.add(tool_name)

        last_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break

        # Comprehensive triggers (safety critical)
        triggers = []

        if used_tools & self.FILE_WRITE_TOOLS:
            triggers.append("file_modification")
        if used_tools & self.EXECUTION_TOOLS:
            triggers.append("code_execution")
        if used_tools & self.AUTOMATION_TOOLS:
            triggers.append("ui_automation")

        for pattern in self.ERROR_PATTERNS:
            if re.search(pattern, last_content, re.MULTILINE):
                triggers.append("error_detected")
                break

        ticket = state.blackboard.ticket
        if ticket and ticket.complexity == "high":
            triggers.append("high_complexity")

        verification = blackboard.verification
        if verification and verification.status in ("failed", "error"):
            triggers.append("verification_failed")

        if len(messages) > 20:
            triggers.append("long_conversation")

        if triggers:
            return AuditDecision("comprehensive", f"safety: {', '.join(triggers)}", 1.0)

        # Minimal tier (strict requirements)
        minimal_ok = [
            used_tools.issubset(self.READONLY_TOOLS),
            len(last_content) > 50,
            len(last_content) < 3000,
            not any(re.search(p, last_content) for p in self.ERROR_PATTERNS),
            not state.is_subtask,
        ]

        if all(minimal_ok):
            return AuditDecision("minimal", "readonly_safe", 0.95)

        return AuditDecision("standard", "default", 0.90)

    async def audit_minimal(self, messages: list, blackboard: "BlackboardState") -> tuple[str, dict]:
        """Rule-based audit, < 10ms."""
        last_content = ""
        tool_usage = []

        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break

        # Fallback to last ToolMessage if no AIMessage with content (common in single-shot workers)
        if not last_content:
            from langchain_core.messages import ToolMessage
            for msg in reversed(messages):
                if isinstance(msg, ToolMessage) and msg.content:
                    last_content = str(msg.content)
                    break

        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get('name') if isinstance(tc, dict) else getattr(tc, 'name', None)
                    if name:
                        tool_usage.append(name)

        # Truncate content directly without prefix
        max_len = 2000
        summary = last_content[:max_len] if len(last_content) <= max_len else last_content[:max_len] + "\n\n[Truncated]"

        return summary, {'tier': 'minimal', 'duration_ms': 5, 'tools': list(set(tool_usage))}

    async def audit_standard(self, messages: list, blackboard: "BlackboardState", state: "AgentState", config: RunnableConfig) -> tuple[str, dict]:
        """Lightweight LLM audit, ~500-800ms."""
        start = time.time()

        tool_usage = []
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get('name') if isinstance(tc, dict) else getattr(tc, 'name', None)
                    if name:
                        tool_usage.append(name)

        last_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break

        # Use FinishPromptBuilder for consistency
        builder = FinishPromptBuilder(
            current_plan=state.current_plan or "",
            execution_ticket=blackboard.ticket,
            verification_status=blackboard.verification,
            action_context=_extract_tool_usage(messages),
            iteration_count=state.iteration_count or 0,
            project_id=state.project_id or DEFAULT_PROJECT_ID,
            blackboard=blackboard,
            session_goal=state.session_goal,
        )
        prompt = builder.build_standard_prompt(last_content, list(set(tool_usage)))

        try:
            from app.core.llm import InternalLLMService
            response = await InternalLLMService.invoke(
                messages=[{"role": "system", "content": prompt}],
                purpose="audit_summary",
                temperature=0.1,
                max_tokens=500,
            )
            summary = str(response.content).strip() if hasattr(response, 'content') else str(response).strip()
            if len(summary) < 20:
                summary = f"Task completed. {summary}"
        except Exception as e:
            logger.error(f"[Auditor] Standard audit failed: {e}")
            summary = f"Task completed.\n\n{last_content[:1000]}"

        duration = (time.time() - start) * 1000
        return summary, {'tier': 'standard', 'duration_ms': duration}


# Global auditor
_auditor: LayeredAuditor = None


def _get_auditor() -> LayeredAuditor:
    global _auditor
    if _auditor is None:
        _auditor = LayeredAuditor()
    return _auditor


async def _comprehensive_audit(state: AgentState, config: RunnableConfig) -> StateUpdate:
    """Original comprehensive audit logic."""
    ctx = ContextManager.current()
    messages = list(state.messages)
    blackboard = state.blackboard

    current_plan = (state.current_plan or "")
    execution_ticket = state.blackboard.ticket
    verification_status = blackboard.verification or VerificationStatus(status="unverified")
    action_context = _extract_tool_usage(messages)

    iteration_count = (state.iteration_count or 0)
    project_id = ctx.project_id or state.project_id or DEFAULT_PROJECT_ID

    from app.core.environment import get_awakened_state
    env_state = get_awakened_state()
    telemetry_data = {}
    if env_state:
        # Use cached telemetry snapshot (1-second TTL) to avoid redundant computation
        telemetry_data = env_state.get_telemetry_snapshot()

    builder = FinishPromptBuilder(
        current_plan=current_plan,
        execution_ticket=execution_ticket,
        verification_status=verification_status,
        action_context=action_context,
        iteration_count=iteration_count,
        project_id=project_id,
        telemetry=telemetry_data,
        blackboard=blackboard,
        session_goal=state.session_goal,
    )
    system_prompt = builder.build()
    audit_ticket = builder.build_audit_ticket()
    tools = await tool_manager.get_node_tools("finish", state)

    logger.info("[Finish] 🕵️ Starting Comprehensive Audit")

    # Prepend audit ticket as HumanMessage so dynamic context is visible to LLM
    messages = list(state.messages)
    if audit_ticket:
        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=audit_ticket, name="audit_ticket")] + messages

    execution_state = state.model_copy(update={"messages": messages})

    # Get user selected model from config (if any)
    model = config.get("configurable", {}).get("model")

    engine = get_default_engine()
    result = await engine.run_node(
        state=execution_state,  # Pass state with audit ticket prepended
        config=config,
        system_prompt=system_prompt,
        tools=tools,
        model=model,  # Use user selected model
        name="Session Reviewer",
        max_steps=settings.FINISH_AGENT_MAX_STEPS,
        node_source="finish",
    )

    return StateUpdate(
        messages=result.messages or [],
        next_node=result.routing_target,
        blackboard=result.blackboard,
        tool_history=result.tool_history,
    )


class FinishNode:
    async def __call__(self, state: AgentState, config: RunnableConfig) -> StateUpdate:
            """
            Layered Finish Node with three-tier auditing.
            """
            start_time = time.time()

            ctx = ContextManager.current()
            messages = list(state.messages)
            blackboard = state.blackboard

            # Robust thread_id fallback for hooks and telemetry
            effective_thread_id = (
                ctx.thread_id
                or state.thread_id
                or config.get("configurable", {}).get("thread_id")
                or "unknown"
            )

            is_shadow_mode = (blackboard.metadata.shadow_audit if blackboard and blackboard.metadata else False) or False

            # 1. Get tool history from blackboard (stored by WorkerNode)
            tool_history = getattr(blackboard.metadata, "tool_history", []) or []

            if is_shadow_mode:
                logger.info("[Finish] 👻 Shadow Mode")
                summary = _extract_final_summary(messages)
                audit_tier = "shadow"
                audit_meta = AuditMeta(tier="shadow", duration_ms=10)
            else:
                # Layered auditing
                auditor = _get_auditor()

                # Classify tier
                decision = auditor.classify_tier(tool_history, messages, blackboard, state)
                audit_tier = decision.tier

                logger.info(f"[Finish] Audit tier: {audit_tier.upper()} ({decision.reason})")

                # Execute audit
                if audit_tier == "minimal":
                    summary, audit_meta = await auditor.audit_minimal(messages, blackboard)

                elif audit_tier == "standard":
                    summary, audit_meta = await auditor.audit_standard(messages, blackboard, state, config)

                else:  # comprehensive
                    result = await _comprehensive_audit(state, config)
                    messages = result.messages or messages
                    blackboard = result.blackboard or blackboard
                    summary = _extract_final_summary(messages)
                    audit_meta = AuditMeta(tier="comprehensive", duration_ms=(time.time() - start_time) * 1000)

            # Extract outcome
            full_text = "".join([str(m.content) for m in messages if isinstance(m, AIMessage)])
            outcome_match = re.search(r"<evoloop_audit_outcome>(.*?)</evoloop_audit_outcome>", full_text, re.IGNORECASE | re.DOTALL)
            final_outcome = ""
            if outcome_match:
                final_outcome = outcome_match.group(1).strip()
                blackboard.metadata.final_outcome = final_outcome
                logger.info(f"[Finish] 🎯 Outcome: {final_outcome}")

            # Apply summary (unless comprehensive already did)
            if audit_tier != "comprehensive":
                for m in reversed(messages):
                    if isinstance(m, AIMessage) and m.content:
                        m.content = summary
                        break

            # Persist audit metadata to blackboard for downstream observability
            blackboard.metadata.audit_tier = audit_tier
            blackboard.metadata.audit_meta = audit_meta
            blackboard.summary = summary

            total_duration = (time.time() - start_time) * 1000

            # 2. Trigger STOP hook for quality gates (Blocking)
            # This can block completion if quality checks fail
            try:
                from app.core.engine.hooks import HookContext, HookEvent, hook_system
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
                    }
                )
                stop_result = await hook_system.trigger(HookEvent.STOP, stop_ctx, blocking=True)
                if stop_result.block:
                    logger.warning(f"[Finish] 🚫 Stop hook blocked completion: {stop_result.message}")
                    # Add blocking message to output
                    block_msg = AIMessage(content=f"\n\n[Quality Gate Blocked] {stop_result.message}\nPlease address the issues before completing.")
                    # Don't end the session, return to supervisor for more work
                    blackboard.metadata.blocked_by_hook = True
                    blackboard.worker_outcome = "failed"  # Signal Supervisor to reset ticket and re-plan
                    return StateUpdate(
                        messages=messages + [block_msg],
                        next_node=RoutingTarget.SUPERVISOR,
                        blackboard=blackboard,
                    )
            except Exception as e:
                logger.exception(f"[Finish] Stop hook failed: {e}")

            # 3. Successful path -> Trigger SIDE EFFECTS (Decoupled Events)
            logger.info(f"[Finish] ✅ {audit_tier.upper()} audit complete: {total_duration:.0f}ms. Finalizing session...")

            # Model the event data for subscribers
            metadata = config.get("metadata", {})
            run_id = config.get("configurable", {}).get("run_id")
            
            event_data = SessionCompletedData(
                thread_id=effective_thread_id,
                run_id=run_id,
                project_id=ctx.project_id,
                user_id=ctx.user_id,
                messages=messages,
                blackboard_dict=blackboard.model_dump() if hasattr(blackboard, 'model_dump') else {},
                summary=summary,
                outcome=final_outcome,
                audit_tier=audit_tier,
                duration_ms=total_duration,
                original_skill_id=metadata.get("original_skill_id"),
                ticket_topic=blackboard.ticket.topic if blackboard.ticket else None,
                ticket_reason=blackboard.ticket.reason if blackboard.ticket else None,
            )

            # Publish the completion event to the global system bus
            # This triggers monitoring, learning, memory extraction, and other decoupled side effects.
            await system_bus.publish(SessionCompletedEvent(data=event_data))
            logger.info(f"[Finish] 📡 SessionCompletedEvent published for thread {effective_thread_id}")

            # Cleanup pollution
            messages_to_return = list(messages)
            removed_ids = []
            for msg in list(state.messages):
                if isinstance(msg, AIMessage) and msg.content:
                    content = str(msg.content)
                    if "<evoloop_session_audit>" in content and "<evoloop_final_report>" in content and hasattr(msg, 'id') and msg.id:
                        messages_to_return.append(RemoveMessage(id=msg.id))
                        removed_ids.append(msg.id[:8] + "...")

            if removed_ids:
                logger.info(f"[Finish] 🗑️ Removed {len(removed_ids)} previous auditor messages")

            # 4. Automatic State Pruning (Prevention of bloat)
            asyncio.create_task(auto_prune_on_completion(effective_thread_id))

            return StateUpdate(
                messages=messages_to_return,
                next_node=RoutingTarget.END,
                blackboard=blackboard,
            )
