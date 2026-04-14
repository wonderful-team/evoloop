import logging
from typing import Any, Optional

from pydantic import BaseModel, Field
from app.infrastructure.pydantic_base import DynamicBaseModel

from app.core.context.manager import ContextManager
from app.core.tools.base import evoloop_tool

logger = logging.getLogger(__name__)


class SynthesizeSkillInput(DynamicBaseModel):
    reason: str = Field(
        ..., 
        description="Reason for triggering skill synthesis. Explain why this session is valuable (e.g., 'Successfully solved a complex bug', 'Implemented a new reusable component')."
    )
    thread_id: Optional[str] = Field(
        None, 
        description="The thread ID to synthesize. Defaults to current thread if not provided."
    )


@evoloop_tool(
    args_schema=SynthesizeSkillInput,
    is_state_mutating=False,
    name_map={"zh": "合成技能", "en": "Synthesize Skill"}
)
async def synthesize_skill(reason: str, thread_id: Optional[str] = None) -> str:
    """
    Manually trigger skill synthesis for the current or a specific thread.
    Use this when you have successfully completed a non-trivial task that 
    could be useful for future reference or tool creation.
    """
    ctx = ContextManager.current()
    target_thread = thread_id or (ctx.thread_id if ctx else None)
    project_id = ctx.project_id if ctx else 0

    if not target_thread:
        return "Error: Could not determine thread_id for synthesis."

    logger.info(f"[Tool] Agent triggered manual skill synthesis for thread {target_thread}. Reason: {reason}")
    
    try:
        from app.infrastructure.queue.factory import get_scheduler
        
        # Trigger the recording task with auto_synthesize=True
        get_scheduler().send_task(
            "engine_record_episode",
            kwargs={
                "thread_id": target_thread,
                "project_id": project_id,
                "auto_synthesize": True
            },
            queue="default"
        )
        return f"Successfully triggered skill synthesis for thread {target_thread}. The system will now analyze the execution trace and synthesize new skills in the background."
    except Exception as e:
        logger.error(f"Failed to trigger synthesis tool: {e}")
        return f"Error: Failed to dispatch synthesis task: {str(e)}"
