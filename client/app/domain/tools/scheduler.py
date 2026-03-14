import logging
from typing import Any, Optional

from app.core.config import settings
from app.core.tools.base import evoloop_tool
from app.infrastructure.database.sql.database import session_scope
from app.models.scheduler import AutonomousTask
from sqlalchemy import select


logger = logging.getLogger(__name__)


@evoloop_tool
async def delegate_periodic_intent(
    intent: str,
    trigger: str,
    skill_name: str,
    params: Optional[dict[str, Any]] = None,
    project_id: Optional[int] = None
) -> str:
    """
    Delegate a recurring high-level intent to the autonomous scheduler.

    NOTE: In client mode, autonomous tasks are managed by the cloud scheduler.
    This tool forwards the request to the cloud API.

    Args:
        intent: High-level description of the goal (e.g. "Daily Xianyu price check for iPhone 15")
        trigger: Cron expression (e.g. "0 12 * * *") or interval spec (e.g. "interval:3600")
        skill_name: The name of the learned skill to use for this task.
        params: Optional parameter overrides for the skill.
        project_id: Optional project context ID.

    Returns:
        A success message with the assigned Task ID, or an error message.
    """
    # REMOVED: Local LearnedSkill lookup (moved to cloud)
    # Client should use cloud API for skill resolution and task scheduling
    logger.debug(f"[Scheduler] Delegating intent '{intent}' with skill '{skill_name}' (cloud API)")
    return "[Client Mode] Autonomous task scheduling is handled via Cloud API. Please use the web interface."


@evoloop_tool
async def inspect_task_health(task_id: int) -> str:
    """
    Inspect the health and execution history of an autonomous task.
    Useful for diagnosing why a recurring task might be failing.
    
    Args:
        task_id: The ID of the autonomous task to inspect.
        
    Returns:
        A detailed report of the task status, failure counts, and last failure reason.
    """
    try:
        async with session_scope() as session:
            task = await session.get(AutonomousTask, task_id)
            if not task:
                return f"Error: Task ID {task_id} not found."
            
            status = "Dead Letter (Disabled)" if task.is_dead_letter else ("Active" if task.is_active else "Paused")
            
            report = (
                f"### Task Health Report: {task_id}\n"
                f"- **Intent**: {task.intent_description}\n"
                f"- **Status**: {status}\n"
                f"- **Consecutive Failures**: {task.consecutive_failures}/{task.max_retries}\n"
                f"- **Last Run**: {task.last_run_at}\n"
                f"- **Next Run**: {task.next_run_at}\n"
                f"- **Last Failure Reason**: {task.last_failure_reason or 'None'}\n"
            )
            
            return report
    except Exception as e:
        logger.error(f"Error in inspect_task_health: {e}")
        return f"Error: Failed to inspect task health. {str(e)}"


@evoloop_tool
async def list_autonomous_tasks(project_id: Optional[int] = None) -> str:
    """
    List all autonomous tasks managed by the agent.
    
    Args:
        project_id: Optional filter by project ID.
        
    Returns:
        A summary list of active tasks.
    """
    try:
        async with session_scope() as session:
            stmt = select(AutonomousTask)
            if project_id:
                stmt = stmt.where(AutonomousTask.project_id == project_id)
            
            result = await session.execute(stmt)
            tasks = result.scalars().all()
            
            if not tasks:
                return "No autonomous tasks found."
            
            lines = ["### Autonomous Task List"]
            for t in tasks:
                status = "DLQ" if t.is_dead_letter else ("Active" if t.is_active else "Paused")
                lines.append(f"- ID {t.id}: [{status}] {t.intent_description[:50]}... (Next: {t.next_run_at})")
            
            return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error in list_autonomous_tasks: {e}")
        return f"Error: Failed to list tasks. {str(e)}"
