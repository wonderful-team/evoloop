import logging
import uuid

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.context.manager import ContextManager
from app.core.engine import AgentEngine
from app.core.engine.prompts.finish import FinishPromptBuilder
from app.core.engine.state import AgentState
from app.core.tools.manager import tool_manager

logger = logging.getLogger(__name__)


def _extract_tool_usage(messages: list) -> str:
    """Extract a summary of tools used in the session to prove activity."""
    tools_used = set()
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls:
                tools_used.add(tc["name"])
    if not tools_used:
        return "No specific tools were called. Actions were purely conversational."
    return "Tools utilized during session: " + ", ".join(sorted(tools_used))


def _extract_final_summary(messages: list) -> str:
    """Extract the last AIMessage text as the reviewer's conclusion."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)[:2000]
    return "Session concluded."


def _trigger_session_recording(ctx, config: RunnableConfig, summary: str):
    """
    Unconditionally trigger async side-effects when session ends.
    Always runs regardless of success/failure outcome.
    """
    try:
        thread_id = ctx.thread_id
        project_id = ctx.project_id or 1
        if not thread_id:
            logger.warning("Finish: No thread_id in context, skipping episode recording.")
            return

        message_id = config.get("configurable", {}).get("run_id") or str(uuid.uuid4())

        from app.core.brain.filesystem.manager import BrainFileSystem
        from app.core.brain.filesystem.protocol import MemoryZone, MemoryFile
        from app.core.brain.tasks import consolidate_memory
        from app.core.engine.tasks import record_episode_task

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
        consolidate_memory.delay(source_message_id=message_id)
        logger.info(f"Finish: ✅ Session recording triggered for thread {thread_id}")

    except Exception as e:
        logger.error(f"Finish: Failed to trigger session recording: {e}")


async def finish_node(state: AgentState, config: RunnableConfig):
    """
    Session Reviewer — Terminal Quality Gate (v5).

    finish is a one-way terminal node: once reached, the session ALWAYS ends.
    The LLM writes a structured conclusion (success or failure) and exits.
    Backtracking is NOT possible — the Supervisor decides when to route here.

    Side effects triggered unconditionally on exit:
      - record_episode_task (Celery async)
      - consolidate_memory (Celery async)
    """
    # 1. Resolve Context
    ctx = ContextManager.current()
    cwd = ctx.working_directory or config.get("configurable", {}).get("working_directory")

    if not cwd:
        logger.error("Finish: No working_directory found. Ending session with error.")
        _trigger_session_recording(ctx, config, "Session ended with missing context.")
        return {"messages": [], "next_node": "END"}

    # 2. Collect context for prompt
    current_plan = state.get("current_plan", "")
    execution_ticket = state.get("execution_ticket")
    verification_status = state.get("verification_status", {})
    messages = state.get("messages", [])
    action_context = _extract_tool_usage(messages)

    # 3. Build Prompt
    builder = FinishPromptBuilder(
        current_plan=current_plan,
        execution_ticket=execution_ticket,
        verification_status=verification_status,
        action_context=action_context
    )
    system_prompt = builder.build()

    # 4. Define Toolset (read/audit tools only — no route_to)
    tools = tool_manager.get_node_tools("finish", state)

    # 5. Run Reviewer Agent
    logger.info(f"Finish: Starting Session Reviewer (cwd={cwd})")
    result = await AgentEngine.run_node(
        state=state,
        config=config,
        system_prompt=system_prompt,
        tools=tools,
        name="Session Reviewer",
        max_steps=20,
    )

    # 6. Always END — trigger recording unconditionally
    last_msgs = result.get("messages", [])
    summary = _extract_final_summary(last_msgs)
    _trigger_session_recording(ctx, config, summary)

    logger.info("Finish: ✅ Session concluded. Recording triggered. Routing to END.")
    return {**result, "next_node": "END"}
