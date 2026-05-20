import json
import logging
from typing import List, Dict, Any

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.evocloud import evocloud_manager
from app.core.tools import evoloop_tool
from app.domain.project.subtask_service import subtask_service
from app.domain.project.sync_tasks import sync_tasks_to_evocloud_task

logger = logging.getLogger(__name__)


@evoloop_tool(
    summary_template="evoloop.tool_summary.create_project_tasks",
)
async def create_project_tasks(
    project_id: int,
    tasks: List[Dict[str, Any]],
    source_context: str | None = None
) -> str:
    """
    Create a list of project tasks and sync them to EvoCloud.
    This is the core tool for requirement breakdown and task planning.
    
    Args:
        project_id: Local project ID to associate with.
        tasks: List of task definitions. Each task can have:
            - title: Task name (Required)
            - description: Detailed explanation
            - priority: high/medium/low
            - estimated_hours: Estimated time to complete
            - subtasks: Optional list of sub-task dicts
        source_context: Optional context about where these tasks came from (e.g., "From requirement doc X").
    """
    try:
        created_task_ids = []
        
        for task_def in tasks:
            # Create task with subtasks using the service
            parent_task = await subtask_service.create_task_with_subtasks(
                project_id=project_id,
                title=task_def.get("title", "Untitled Task"),
                analysis_id=None,  # Independent of requirement analysis
                description=task_def.get("description", source_context or ""),
                priority=task_def.get("priority", "medium"),
                estimated_hours=task_def.get("estimated_hours", 0),
                subtasks=task_def.get("subtasks", [])
            )
            
            created_task_ids.append(parent_task.id)
            # Add subtask IDs for sync
            for sub in parent_task.subtasks:
                created_task_ids.append(sub.id)

        # Trigger background sync to EvoCloud
        if created_task_ids:
            sync_tasks_to_evocloud_task.delay(task_ids=created_task_ids)
            
        return json.dumps({
            "success": True,
            "created_count": len(tasks),
            "total_records": len(created_task_ids),
            "message": f"Successfully created {len(tasks)} tasks and triggered cloud sync."
        })

    except Exception as e:
        logger.exception(f"Failed to create project tasks: {e}")
        return json.dumps({
            "success": False,
            "error": str(e)
        })


@evoloop_tool(
    is_state_mutating=True,
    summary_template="evoloop.tool_summary.create_project_task"
)
async def create_project_task(project_id: int | None = None, task_data: str = "") -> str:
    """
    Create a single task in the remote project management system via EvoCloud.
    (Maintained for legacy compatibility; preferred tool is create_project_tasks)

    Args:
        project_id (int): The ID of the project to add the task to. Optional.
        task_data (str): JSON string representation of the task data (title, desc, priority, etc.).
    """
    ctx_pid = ContextManager.current().project_id
    pid = project_id if project_id is not None else (ctx_pid if ctx_pid is not None else DEFAULT_PROJECT_ID)

    try:
        if isinstance(task_data, str):
            task_dict = json.loads(task_data)
        else:
            task_dict = task_data

        task_dict["project_id"] = pid
        response = await evocloud_manager.api.create_task(data=task_dict)

        if response.get("code") == 0:
            return f"Success: Task created with ID {response.get('data', {}).get('task_id')}"
        else:
            return f"Failed: {response.get('message')}"
    except Exception as e:
        logger.error(f"Task creation failed: {e}")
        return f"Error: {str(e)}"
