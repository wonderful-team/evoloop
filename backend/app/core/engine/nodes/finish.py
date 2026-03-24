import logging
import re

from langchain_core.messages import AIMessage

from app.utils.id import gen_uuid
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.engine import AgentEngine
from app.core.engine.prompts.finish import FinishPromptBuilder
from app.core.engine.state import AgentState
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
            # 1. Standard tool_calls attribute
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                    if name:
                        tools_used.add(name)
            # 2. Legacy/Provider-specific additional_kwargs
            elif msg.additional_kwargs and "tool_calls" in msg.additional_kwargs:
                for tc in msg.additional_kwargs["tool_calls"]:
                    name = tc.get("function", {}).get("name") if "function" in tc else tc.get("name")
                    if name:
                        tools_used.add(name)
        elif isinstance(msg, ToolMessage) or (hasattr(msg, "tool_call_id") and msg.tool_call_id):
            # 3. Direct ToolMessage check (fallback for when AI message link is lost)
            name = getattr(msg, "name", None)
            if name:
                tools_used.add(name)

    # Use PerceptionsFormatter for consistent output formatting
    from app.utils import PerceptionsFormatter
    formatted = PerceptionsFormatter.tools_used(tools_used)

    if not formatted or formatted.strip() == "":
        if not tools_used:
            return "No tool actions were recorded in this session. The conversation may have concluded with text responses only."
        return f"Tools utilized in this session: {', '.join(sorted(tools_used))}"

    return formatted


def _extract_final_summary(messages: list) -> str:
    """Extract the last AIMessage text as the reviewer's conclusion, stripping technical markers."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            content = str(msg.content)
            
            # 1. Structural Extraction (Systematic Review)
            # Prioritize content within <report> tags
            report_match = re.search(r"<report>(.*?)</report>", content, flags=re.DOTALL | re.IGNORECASE)
            if report_match:
                return report_match.group(1).strip()

            # 2. Fallback: Strip XML-based audit tags
            content = re.sub(r"<(audit|outcome|reason|proof_points)>.*?</\1>", "", content, flags=re.DOTALL | re.IGNORECASE)
            # Remove any other leftover XML tags (like <thought>, <status>, etc.)
            content = re.sub(r"<[^>]+>", "", content)
            
            # 3. Language-Agnostic Header Peeling
            # Instead of a hardcoded list, we strip lines that look like "Header: " 
            # (e.g., "Summary: ", "最终总结: ", "结论: ")
            # regex: start of line, 1-25 chars (excluding newline/tags), followed by colon and optional space
            content = re.sub(r"^\s*[^:\n]{1,25}:\s*", "", content, flags=re.MULTILINE)
            
            # 4. Cleanup and Trim
            # We no longer blacklist specific icons or markers, but trim the text
            # and remove code blocks to ensure a clean narrative.
            content = content.replace("```", "").strip()
            
            return content[:2000]
    return i18n.get("finish.session_concluded", default="Session concluded.")


def _trigger_session_recording(ctx, config: RunnableConfig, summary: str, original_skill_id: int | None = None):
    """
    Unconditionally trigger async side-effects when session ends.
    Always runs regardless of success/failure outcome.
    """
    try:
        thread_id = ctx.thread_id
        project_id = ctx.project_id or DEFAULT_PROJECT_ID
        if not thread_id:
            logger.warning("Finish: No thread_id in context, skipping episode recording.")
            return

        message_id = config.get("configurable", {}).get("run_id") or gen_uuid()

        from app.core.brain.filesystem.manager import BrainFileSystem
        from app.core.brain.filesystem.protocol import MemoryZone, MemoryFile
        from app.core.brain.tasks import consolidate_memory
        from app.core.engine.tasks import record_episode_task, reconcile_skill_macro_task

        # Bridge: Sync to Brain Working Memory (for Consolidation Cycle)
        try:
            fs = BrainFileSystem(settings.BRAIN_MEMORY_ROOT)
            fs.initialize()
            task_path = f"{MemoryZone.WORKING.value}/{MemoryFile.TASK.value}"
            fs.write_file(task_path, summary)
            logger.info(f"Finish: 🧠 Synced session summary to Brain memory: {task_path}")
        except Exception as brain_err:
            logger.warning(f"Finish: Failed to sync to brain memory: {brain_err}")

        record_episode_task.delay(
            thread_id=thread_id,
            project_id=project_id,
            goal="[Auto-recorded by Finish Node]",
            result_summary=summary,
            concept_names=[],
            source_message_id=message_id,
        )
        
        # Phase 8: Learning Loop - Update original skill macro if this was a recovery session
        if original_skill_id:
            logger.info(f"Finish: 🔄 Triggering macro reconciliation for Skill {original_skill_id}")
            reconcile_skill_macro_task.delay(
                skill_id=original_skill_id,
                thread_id=thread_id
            )
            
        consolidate_memory.delay(source_message_id=message_id)
        logger.info(f"Finish: ✅ Session recording triggered for thread {thread_id}")

    except Exception as e:
        logger.error(f"Finish: Failed to trigger session recording: {e}")


async def finish_node(state: AgentState, config: RunnableConfig):
    """
    Session Reviewer — Shadow Observer / Terminal Gate.
    
    [ARCHITECTURAL NOTE]
    This node receives the FULL conversation history from the state.
    The history may contain messages from previous Session Reviewer runs,
    which should NOT influence the current audit.
    
    Strategy:
    1. Use smart_window_slice to get recent relevant context
    2. The Session Reviewer generates a final summary
    3. We return a CLEAN message list to prevent pollution of future runs
    """
    # 1. Resolve Context
    ctx = ContextManager.current()
    messages = state.get("messages", [])
    
    # Check if we should skip the LLM auditor (Shadow Mode)
    # This is enabled when the LLM concludes naturally with text.
    blackboard = state.get("blackboard") or {}
    is_shadow_mode = blackboard.get("metadata", {}).get("shadow_audit", False)
    
    summary = ""
    if is_shadow_mode:
        logger.info("[Finish] 👻 Running in Shadow Mode (Natural Termination)")
        summary = _extract_final_summary(messages)
    else:
        # Legacy/Explicit Audit Path
        current_plan = state.get("current_plan", "")
        execution_ticket = blackboard.get("ticket") or state.get("execution_ticket")
        verification_status = blackboard.get("verification") or state.get("verification_status", {})
        action_context = _extract_tool_usage(messages)

        # Phase 8: Strategic Context Injection (Design Audit Fix)
        iteration_count = state.get("iteration_count", 0)
        project_id = ctx.project_id or state.get("project_id") or DEFAULT_PROJECT_ID
        
        from app.core.environment import get_awakened_state
        env_state = get_awakened_state()
        telemetry_data = {}
        if env_state:
            telemetry_data = {
                "android": [{"id": d.device_id, "reachable": d.is_reachable} for d in env_state.android_devices],
                "macos": bool(env_state.macos),
                "network": env_state.network.internet_connected if env_state.network else False
            }

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

        logger.info("[Finish] 🕵️ Starting Explicit Session Audit")
        
        # Use smart windowing to get relevant context without overwhelming the LLM
        from app.core.engine.message_utils import smart_window_slice
        windowed_messages = smart_window_slice(messages, window_size=10)
        
        # Create focused state for the auditor
        focused_state = dict(state)
        focused_state["messages"] = windowed_messages
        
        result = await AgentEngine.run_node(
            state=focused_state,
            config=config,
            system_prompt=system_prompt,
            tools=tools,
            name="Session Reviewer",
            max_steps=settings.FINISH_AGENT_MAX_STEPS,
        )
        messages = result.get("messages", [])
        blackboard = result.get("blackboard", blackboard)
        summary = _extract_final_summary(messages)

    # Sync Structured Outcome to Blackboard for UI/Analytics
    # This outcome is used by the frontend to show success/failure indicators.
    # MUST extract before message cleaning below
    full_text = "".join([str(m.content) for m in messages if isinstance(m, AIMessage)])
    outcome_match = re.search(r"<outcome>(.*?)</outcome>", full_text, re.IGNORECASE | re.DOTALL)
    final_outcome = ""
    if outcome_match:
        final_outcome = outcome_match.group(1).strip()
        blackboard.setdefault("metadata", {})["final_outcome"] = final_outcome
        logger.info(f"[Finish] {i18n.get('icons.rocket', default='🎯')} Detected structured outcome: {final_outcome}")

    # [PHASE 6 REPAIR] Deep Cleaning — apply summary cleanup to the returned message
    # This ensures the user UI sees the "peeled" pure summary, not the raw XML tags.
    # We do this AFTER outcome extraction to preserve the tags for analysis
    for m in reversed(messages):
        if isinstance(m, AIMessage) and m.content:
            m.content = summary
            break

    # 2. Finalize Run State
    await activity_monitor.end_run(ctx.thread_id, status="done", final_outcome=final_outcome)

    # 3. Trigger Recording
    metadata = config.get("metadata", {})
    original_skill_id = metadata.get("original_skill_id")
    _trigger_session_recording(ctx, config, summary, original_skill_id=original_skill_id)

    # [CRITICAL FIX] Prevent pollution of future sessions
    # Use RemoveMessage to delete previous Session Reviewer outputs from history
    # This ensures they don't get passed to future LLM calls
    from langchain_core.messages import RemoveMessage

    messages_to_return = list(messages)  # Copy the list
    removed_ids = []

    # Identify and mark messages from previous Session Reviewer runs for deletion
    # These are typically AIMessages without tool_calls and with specific patterns
    for msg in state.get("messages", []):
        if isinstance(msg, AIMessage) and msg.content:
            content = str(msg.content)
            # Detect previous Session Reviewer outputs (pollution sources)
            # They typically contain structured audit reports or meta-markers
            if "<audit>" in content and "<report>" in content and hasattr(msg, 'id') and msg.id:
                messages_to_return.append(RemoveMessage(id=msg.id))
                removed_ids.append(msg.id[:8] + "...")

    if removed_ids:
        logger.info(f"[Finish] 🗑️ Marked {len(removed_ids)} previous Session Reviewer messages for removal: {removed_ids}")

    logger.info(f"Finish: {i18n.get('icons.success', default='✅')} Session concluded with outcome {final_outcome or 'DONE'}. Routing to END.")
    return {
        "messages": messages_to_return, 
        "next_node": "END",
        "blackboard": blackboard
    }
