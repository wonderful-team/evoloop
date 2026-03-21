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
from app.constants import DEFAULT_PROJECT_ID, TECHNICAL_MARKERS, STATUS_ICONS
from app.i18n.service import i18n

logger = logging.getLogger(__name__)


def _extract_tool_usage(messages: list) -> str:
    """Extract a summary of tools used in the session to prove activity."""
    tools_used = set()
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
                tools_used.add(tc["name"])
    if not tools_used:
        # Avoid hardcoded string, but since this is internally logged mostly, 
        # we'll use a generic placeholder or add to i18n if needed.
        return "No specific tools were called."
    return "Tools: " + ", ".join(sorted(tools_used))


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
            # Remove any orphan/leftover XML tags
            content = re.sub(r"<[^>]+>", "", content)
            
            # 3. Language-Agnostic Header Peeling
            # Instead of a hardcoded list, we strip lines that look like "Header: " 
            # (e.g., "Summary: ", "最终总结: ", "结论: ")
            # regex: start of line, 1-20 chars (excluding newline/tags), followed by colon and optional space
            content = re.sub(r"^\s*[^:\n]{1,20}:\s*", "", content, flags=re.MULTILINE)
            
            # 4. Icon & Delimiter Cleanup (Using decentralized constants)
            # Matches status icons and technical markers
            icons_pattern = "[" + "".join([re.escape(i) for i in STATUS_ICONS.values()]) + "]"
            content = re.sub(icons_pattern, "", content)
            
            markers_pattern = r"(" + "|".join([re.escape(m) for m in TECHNICAL_MARKERS]) + r"):?\s*"
            content = re.sub(markers_pattern, "", content, flags=re.IGNORECASE)
            
            # 5. Clean backticks/code blocks and trim
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

        builder = FinishPromptBuilder(
            current_plan=current_plan,
            execution_ticket=execution_ticket,
            verification_status=verification_status,
            action_context=action_context
        )
        system_prompt = builder.build()
        tools = tool_manager.get_node_tools("finish", state)

        logger.info("[Finish] 🕵️ Starting Explicit Session Audit")
        result = await AgentEngine.run_node(
            state=state,
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

    logger.info(f"Finish: {i18n.get('icons.success', default='✅')} Session concluded with outcome {final_outcome or 'DONE'}. Routing to END.")
    return {
        "messages": messages, 
        "next_node": "END",
        "blackboard": blackboard
    }
