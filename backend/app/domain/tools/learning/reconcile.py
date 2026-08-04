import logging

from app.core.engine.tasks import reconcile_skill_macro_task
from app.core.tools import evoloop_tool

logger = logging.getLogger(__name__)


@evoloop_tool(summary_template="evoloop.tool_summary.reconcile_skill")
async def reconcile_skill(skill_id: int, thread_id: str) -> str:
    """
    Self-heal a skill by reconciling its broken macro with a successful execution trace.
    Use this AFTER you have successfully performed the action using your reasoning or
    after a human has helped you recover. This will update the skill's deterministic macro
    so it works automatically next time.

    Args:
        skill_id: The ID of the skill to repair.
        thread_id: The current thread ID containing the successful recovery trace.

    Returns:
        A message indicating if the reconciliation was triggered.
    """
    try:
        # Trigger the Celery task to perform the heavy lifting of synthesis and patching
        reconcile_skill_macro_task.delay(skill_id=skill_id, thread_id=thread_id)
        return f"Successfully triggered self-healing for Skill {skill_id} using trace from thread {thread_id}."
    except Exception as e:
        logger.error(f"Error triggering reconcile_skill: {e}")
        return f"Error: Failed to trigger self-healing. {str(e)}"
