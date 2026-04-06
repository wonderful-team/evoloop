import asyncio
import json
import logging
import re
import time

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.utils.id import gen_uuid
from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.engine import AgentEngine
from app.core.engine.prompts.finish import FinishPromptBuilder
from app.core.engine.state import AgentState
from app.infrastructure.llm.factory import LLMFactory
from app.core.monitoring.activity import activity_monitor
from app.core.tools.manager import tool_manager
from app.constants import DEFAULT_PROJECT_ID
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
            
            report_match = re.search(r"<report>(.*?)</report>", content, flags=re.DOTALL | re.IGNORECASE)
            if report_match:
                return report_match.group(1).strip()

            content = re.sub(r"<(audit|outcome|reason|proof_points)>.*?</\1>", "", content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r"<[^>]+>", "", content)
            content = re.sub(r"^\s*[^:\n]{1,25}:\s*", "", content, flags=re.MULTILINE)
            content = content.replace("```", "").strip()
            
            return content[:2000]
    return i18n.get("finish.session_concluded")


async def _trigger_session_recording(ctx, config: RunnableConfig, summary: str, original_skill_id: int | None = None, execution_ticket: dict | None = None):
    """Trigger async side-effects when session ends."""
    try:
        thread_id = ctx.thread_id
        project_id = ctx.project_id or DEFAULT_PROJECT_ID
        if not thread_id:
            logger.warning("Finish: No thread_id in context, skipping episode recording.")
            return

        message_id = config.get("configurable", {}).get("run_id") or gen_uuid()

        from app.core.memory.models import MemoryEntry, MemoryType, PrivacyLevel
        from app.core.engine.tasks import record_episode_task, reconcile_skill_macro_task
        from app.core.memory.lifespan import MemoryLifespanManager

        try:
            # Save session summary as a PROJECT memory
            task_description = summary
            if execution_ticket:
                ticket_topic = execution_ticket.get("topic")
                ticket_reason = execution_ticket.get("reason")
                if ticket_topic and len(ticket_topic) > 10:
                    task_description = f"Task: {ticket_topic}\n\nOutcome:\n{summary}"
                elif ticket_reason and len(ticket_reason) > 10:
                    task_description = f"Task: {ticket_reason}\n\nOutcome:\n{summary}"
            
            entry = MemoryEntry(
                id=f"mem_session_{message_id[:8]}",
                type=MemoryType.PROJECT,
                privacy=PrivacyLevel.TEAM if project_id else PrivacyLevel.PRIVATE,
                title=f"Session Summary {thread_id[:8]}",
                content=task_description,
                description=summary[:200],
                project_id=project_id,
                source="session",
                source_message_id=message_id,
            )
            # Use global singleton container to save memory
            if not MemoryLifespanManager.is_initialized():
                await MemoryLifespanManager.ainitialize()
            await MemoryLifespanManager.get_manager().save_memory(entry)
            logger.info(f"Finish: 🧠 Synced session summary to memory: {entry.id}")
        except Exception as mem_err:
            logger.warning(f"Finish: Failed to sync to memory: {mem_err}")

        # Determine a friendly goal for the Episode
        episode_goal = "[Auto-recorded by Finish Node]"
        if execution_ticket:
            ticket_topic = execution_ticket.get("topic")
            ticket_reason = execution_ticket.get("reason")
            if ticket_topic and len(ticket_topic) > 5:
                episode_goal = ticket_topic
            elif ticket_reason and len(ticket_reason) > 5:
                episode_goal = ticket_reason

        record_episode_task.delay(
            thread_id=thread_id,
            project_id=project_id,
            goal=episode_goal,
            result_summary=summary,
            concept_names=[],
            source_message_id=message_id,
        )
        
        if original_skill_id:
            logger.info(f"Finish: 🔄 Triggering macro reconciliation for Skill {original_skill_id}")
            reconcile_skill_macro_task.delay(
                skill_id=original_skill_id,
                thread_id=thread_id
            )
            
        logger.info(f"Finish: ✅ Session recording triggered for thread {thread_id}")

    except Exception as e:
        logger.error(f"Finish: Failed to trigger session recording: {e}")


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
    
    def __init__(self):
        self._fast_llm = None
    
    async def _get_fast_llm(self):
        if self._fast_llm is None:
            self._fast_llm = await LLMFactory.create_llm(temperature=0.1, max_tokens=500)
        return self._fast_llm
    
    def classify_tier(self, tool_history: list, messages: list, blackboard: dict, state: dict) -> AuditDecision:
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
        
        ticket = blackboard.get("ticket") or {}
        if ticket.get("complexity") == "high":
            triggers.append("high_complexity")
        
        verification = blackboard.get("verification") or {}
        if verification.get("status") in ("failed", "error"):
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
            not state.get("is_subtask"),
        ]
        
        if all(minimal_ok):
            return AuditDecision("minimal", "readonly_safe", 0.95)
        
        return AuditDecision("standard", "default", 0.90)
    
    async def audit_minimal(self, messages: list, blackboard: dict) -> tuple[str, dict]:
        """Rule-based audit, < 10ms."""
        last_content = ""
        tool_usage = []
        
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = str(msg.content)
                break
        
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get('name') if isinstance(tc, dict) else getattr(tc, 'name', None)
                    if name:
                        tool_usage.append(name)
        
        # Generate prefix based on operation
        if 'read_file' in tool_usage:
            prefix = "📄 File content retrieved successfully.\n\n"
        elif 'search_files' in tool_usage or 'search_web' in tool_usage:
            prefix = "🔍 Search completed. Found relevant results.\n\n"
        elif 'list_directory' in tool_usage:
            prefix = "📁 Directory listing complete.\n\n"
        elif 'analyze_image' in tool_usage:
            prefix = "🖼️ Image analysis complete.\n\n"
        else:
            prefix = "✅ Operation completed successfully.\n\n"
        
        max_len = 2000
        content = last_content[:max_len] if len(last_content) <= max_len else last_content[:max_len] + "\n\n[Truncated]"
        
        summary = prefix + content
        
        return summary, {'tier': 'minimal', 'duration_ms': 5, 'tools': list(set(tool_usage))}
    
    async def audit_standard(self, messages: list, blackboard: dict, config: RunnableConfig) -> tuple[str, dict]:
        """Lightweight LLM audit, ~500-800ms."""
        start = time.time()
        
        ticket = blackboard.get("ticket", {})
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
        
        prompt = f"""Summarize this session in 2-3 sentences.

Task: {ticket.get('topic', 'Unknown')}
Tools: {', '.join(set(tool_usage)) if tool_usage else 'None'}

Result:
{last_content[:1500]}

Was the task completed? What were the key findings?"""

        try:
            llm = await self._get_fast_llm()
            response = await llm.ainvoke([SystemMessage(content=prompt)])
            summary = str(response.content).strip()
            if len(summary) < 20:
                summary = f"✅ Task completed. {summary}"
        except Exception as e:
            logger.error(f"[Auditor] Standard audit failed: {e}")
            summary = f"✅ Task completed.\n\n{last_content[:1000]}"
        
        duration = (time.time() - start) * 1000
        return summary, {'tier': 'standard', 'duration_ms': duration}


# Global auditor
_auditor: LayeredAuditor = None

def _get_auditor() -> LayeredAuditor:
    global _auditor
    if _auditor is None:
        _auditor = LayeredAuditor()
    return _auditor


async def _comprehensive_audit(state: AgentState, config: RunnableConfig) -> dict:
    """Original comprehensive audit logic."""
    ctx = ContextManager.current()
    messages = state.get("messages", [])
    blackboard = state.get("blackboard") or {}
    
    current_plan = state.get("current_plan", "")
    execution_ticket = blackboard.get("ticket") or state.get("execution_ticket")
    verification_status = blackboard.get("verification") or state.get("verification_status", {})
    action_context = _extract_tool_usage(messages)

    iteration_count = state.get("iteration_count", 0)
    project_id = ctx.project_id or state.get("project_id") or DEFAULT_PROJECT_ID
    
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
        blackboard=blackboard
    )
    system_prompt = builder.build()
    tools = tool_manager.get_node_tools("finish", state)

    logger.info("[Finish] 🕵️ Starting Comprehensive Audit")
    
    # Note: AgentEngine.run_node will handle smart_window_slice internally
    # No need to pre-slice here, avoiding redundant operations
    
    # Get user selected model from config (if any)
    model = config.get("configurable", {}).get("model")
    
    result = await AgentEngine.run_node(
        state=state,  # Pass original state, let AgentEngine handle slicing
        config=config,
        system_prompt=system_prompt,
        tools=tools,
        model=model,  # Use user selected model
        name="Session Reviewer",
        max_steps=settings.FINISH_AGENT_MAX_STEPS,
        node_source="finish",
    )
    
    return result


async def finish_node(state: AgentState, config: RunnableConfig):
    """
    Layered Finish Node with three-tier auditing.
    """
    start_time = time.time()
    
    ctx = ContextManager.current()
    messages = state.get("messages", [])
    blackboard = state.get("blackboard") or {}
    
    is_shadow_mode = blackboard.get("metadata", {}).get("shadow_audit", False)
    
    if is_shadow_mode:
        logger.info("[Finish] 👻 Shadow Mode")
        summary = _extract_final_summary(messages)
        audit_tier = "shadow"
        audit_meta = {"tier": "shadow", "duration_ms": 10}
    else:
        # Layered auditing
        auditor = _get_auditor()
        
        # Extract tool history
        tool_history = []
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get('name') if isinstance(tc, dict) else getattr(tc, 'name', None)
                    args = tc.get('args', {}) if isinstance(tc, dict) else getattr(tc, 'args', {})
                    if name:
                        tool_history.append(f"{name}:{json.dumps(args, sort_keys=True)}")
        
        # Classify tier
        decision = auditor.classify_tier(tool_history, messages, blackboard, state)
        audit_tier = decision.tier
        
        logger.info(f"[Finish] Audit tier: {audit_tier.upper()} ({decision.reason})")
        
        # Execute audit
        if audit_tier == "minimal":
            summary, audit_meta = await auditor.audit_minimal(messages, blackboard)
            
        elif audit_tier == "standard":
            summary, audit_meta = await auditor.audit_standard(messages, blackboard, config)
            
        else:  # comprehensive
            result = await _comprehensive_audit(state, config)
            messages = result.get("messages", messages)
            blackboard = result.get("blackboard", blackboard)
            summary = _extract_final_summary(messages)
            audit_meta = {"tier": "comprehensive", "duration_ms": (time.time() - start_time) * 1000}
    
    # Extract outcome
    full_text = "".join([str(m.content) for m in messages if isinstance(m, AIMessage)])
    outcome_match = re.search(r"<outcome>(.*?)</outcome>", full_text, re.IGNORECASE | re.DOTALL)
    final_outcome = ""
    if outcome_match:
        final_outcome = outcome_match.group(1).strip()
        blackboard.setdefault("metadata", {})["final_outcome"] = final_outcome
        logger.info(f"[Finish] 🎯 Outcome: {final_outcome}")

    # Apply summary (unless comprehensive already did)
    if audit_tier != "comprehensive":
        for m in reversed(messages):
            if isinstance(m, AIMessage) and m.content:
                m.content = summary
                break

    # Finalize
    await activity_monitor.end_run(ctx.thread_id, status="done", final_outcome=final_outcome)

    metadata = config.get("metadata", {})
    original_skill_id = metadata.get("original_skill_id")
    blackboard_ticket = blackboard.get("ticket") or state.get("execution_ticket")
    await _trigger_session_recording(ctx, config, summary, original_skill_id=original_skill_id, execution_ticket=blackboard_ticket)
    
    # Trigger automatic memory extraction (fire and forget)
    # This runs in background without blocking the response
    try:
        from app.core.memory.auto_extraction import trigger_auto_extraction
        asyncio.create_task(
            trigger_auto_extraction(
                thread_id=ctx.thread_id,
                messages=messages,
                project_id=ctx.project_id,
                user_id=ctx.user_id,
            )
        )
        logger.debug(f"[Finish] Triggered auto-extraction for thread {ctx.thread_id}")
    except Exception as e:
        logger.warning(f"[Finish] Failed to trigger auto-extraction: {e}")

    # Trigger SessionEnd hook for session recording and state persistence
    try:
        from app.core.engine.hooks import hook_system, HookEvent, HookContext
        hook_ctx = HookContext(
            thread_id=ctx.thread_id,
            user_id=ctx.user_id,
            project_id=ctx.project_id,
            messages=messages,
            blackboard=blackboard,
            metadata={
                "summary": summary,
                "audit_tier": audit_tier,
                "final_outcome": final_outcome,
                "tool_count": len(tool_history) if 'tool_history' in locals() else 0,
                "message_count": len(messages),
            }
        )
        await hook_system.trigger(HookEvent.SESSION_END, hook_ctx)
        logger.debug(f"[Finish] SessionEnd hook executed for thread {ctx.thread_id}")
    except Exception as e:
        logger.warning(f"[Finish] SessionEnd hook failed: {e}")

    # Cleanup pollution
    messages_to_return = list(messages)
    removed_ids = []

    for msg in state.get("messages", []):
        if isinstance(msg, AIMessage) and msg.content:
            content = str(msg.content)
            if "<audit>" in content and "<report>" in content and hasattr(msg, 'id') and msg.id:
                messages_to_return.append(RemoveMessage(id=msg.id))
                removed_ids.append(msg.id[:8] + "...")

    if removed_ids:
        logger.info(f"[Finish] 🗑️ Removed {len(removed_ids)} previous auditor messages")

    total_duration = (time.time() - start_time) * 1000
    logger.info(f"[Finish] ✅ {audit_tier.upper()} audit complete: {total_duration:.0f}ms")

    # Trigger STOP hook for quality gates
    # This can block completion if quality checks fail
    try:
        from app.core.engine.hooks import hook_system, HookEvent, HookContext
        stop_ctx = HookContext(
            thread_id=ctx.thread_id,
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
            messages_to_return.append(block_msg)
            # Don't end the session, return to user for fixes
            return {
                "messages": messages_to_return,
                "next_node": "supervisor",  # Return to supervisor for more work
                "blackboard": blackboard,
                "_audit_tier": audit_tier,
                "_audit_meta": audit_meta,
                "_blocked_by_hook": True,
            }
    except Exception as e:
        logger.warning(f"[Finish] Stop hook failed: {e}")

    return {
        "messages": messages_to_return, 
        "next_node": "END",
        "blackboard": blackboard,
        "_audit_tier": audit_tier,
        "_audit_meta": audit_meta,
    }
