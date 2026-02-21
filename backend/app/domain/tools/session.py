import logging
import uuid
from typing import Annotated, List

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.tools import evoloop_tool
from app.core.context.manager import ContextManager

logger = logging.getLogger(__name__)


@evoloop_tool
async def finalize_session(
    summary: str,
    mission_achieved: bool = True,
    follow_up_needed: bool = False,
    concept_names: List[str] | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None
) -> str:
    """
    Terminates the current agent session with a final summary of accomplishments.
    This tool triggers the formal recording of the mission episode and background memory consolidation.
    
    Args:
        summary: Professional summary of what was accomplished.
        mission_achieved: Whether the primary goal of the session was met.
        follow_up_needed: Whether additional tasks remain for future sessions.
        concept_names: List of important concept names that were handled/harvested.
    """
    ctx = ContextManager.current()
    project_id = ctx.project_id or 1
    thread_id = ctx.thread_id
    
    if not thread_id:
        return "Error: No active thread context found."

    # Pre-generate Message ID if not present in config
    message_id = config.get("configurable", {}).get("run_id") or str(uuid.uuid4())

    try:
        from app.core.engine.tasks import record_episode_task
        from app.core.brain.tasks import consolidate_memory
        
        # 1. Dispatch Episode Recording
        # We need the goal (first human message)
        # In a real tool context, we might not have all messages, 
        # but the task handles the rest if we provide metadata.
        record_episode_task.delay(
            thread_id=thread_id,
            project_id=project_id,
            goal="[Finalized via Reviewer]", # The task will refine this if it has DB access
            result_summary=summary,
            concept_names=concept_names or [],
            source_message_id=message_id,
        )
        
        # 2. Trigger Memory Consolidation
        consolidate_memory.delay(source_message_id=message_id)
        
        logger.info(f"Session {thread_id} finalized via Reviewer agent.")
        
        # We return a special token that the finish_node can detect to stop the graph
        return f"[SESSION_FINALIZED] Summary: {summary}"
        
    except Exception as e:
        logger.error(f"Failed to finalize session: {e}")
        return f"Error finalizing session: {str(e)}"
