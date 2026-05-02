import logging
from typing import Any, Optional

from sqlalchemy import select

from app.core.tools import evoloop_tool
from app.infrastructure.database.sql.database import session_scope
from app.models.learning import LearnedSkill
from app.models.scheduler import AutonomousTask
from app.utils import ControllerResponse, SystemToolsFormatter

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_hidden=True,
    summary_template="database_logger.tool_summary.delegate_periodic_intent"
)
async def delegate_periodic_intent(
    intent: str,
    trigger: str,
    skill_name: str,
    params: Optional[dict[str, Any]] = None,
    project_id: Optional[int] = None
) -> str:
    """
    Delegate a recurring high-level intent to the autonomous scheduler.
    
    Args:
        intent: High-level description of the goal (e.g. "Daily Xianyu price check for iPhone 15")
        trigger: Cron expression (e.g. "0 12 * * *") or interval spec (e.g. "interval:3600")
        skill_name: The name of the learned skill to use for this task.
        params: Optional parameter overrides for the skill.
        project_id: Optional project context ID.
        
    Returns:
        A success message with the assigned Task ID, or an error message.
    """
    try:
        from app.infrastructure.scheduler.service import SchedulerService
        async with session_scope() as session:
            # Resolve skill name to ID
            stmt = select(LearnedSkill).where(LearnedSkill.name == skill_name)
            result = await session.execute(stmt)
            skill = result.scalar_one_or_none()
            
            if not skill:
                return ControllerResponse.not_found(skill_name, item_type="Skill")

            task_id = await SchedulerService.register_task(
                intent_description=intent,
                skill_id=skill.id,
                trigger_spec=trigger,
                params=params,
                project_id=project_id
            )
            
            return ControllerResponse.success(
                f"Delegated periodic intent: {intent}",
                details=f"Task ID: {task_id}",
                note=f"Trigger: {trigger}"
            )
    except Exception as e:
        logger.error(f"Error in delegate_periodic_intent: {e}")
        return ControllerResponse.error("Failed to delegate intent", details=str(e))


@evoloop_tool(summary_template="database_logger.tool_summary.inspect_task_health")
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
                return ControllerResponse.not_found(f"Task ID {task_id}")
            
            status = "Dead Letter (Disabled)" if task.is_dead_letter else ("Active" if task.is_active else "Paused")
            
            try:
                return SystemToolsFormatter.task_health(task)
            except Exception as e:
                logger.error(f"Failed to render task health: {e}")
                return f"Task {task_id} health: {status}"
    except Exception as e:
        logger.error(f"Error in inspect_task_health: {e}")
        return f"Error: Failed to inspect task health. {str(e)}"


@evoloop_tool(summary_template="database_logger.tool_summary.list_autonomous_tasks")
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
            
            try:
                return SystemToolsFormatter.autonomous_tasks(tasks)
            except Exception as e:
                logger.error(f"Failed to render task list: {e}")
                return f"Found {len(tasks)} tasks."
    except Exception as e:
        logger.error(f"Error in list_autonomous_tasks: {e}")
        return f"Error: Failed to list tasks. {str(e)}"
