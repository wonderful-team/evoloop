import json
import logging
from typing import Optional
from app.logging import get_context

from langchain_core.tools import tool


logger = logging.getLogger(__name__)


@tool
async def create_project_task(project_id: Optional[int] = None, task_data: str = "") -> str:
    """
    Create a task in the remote project management system via ImagicBox.
    
    Args:
        project_id (int): The ID of the project to add the task to. Optional.
        task_data (str): JSON string representation of the task data (title, desc, priority, etc.).
    """
    pid = project_id or get_context().get("project_id", 1)
    
    try:
        from app.infrastructure.external.imagicbox import imagicbox_client
        
        # Parse task data if it's a string
        if isinstance(task_data, str):
            try:
                task_dict = json.loads(task_data)
            except json.JSONDecodeError:
                return "Error: task_data is not valid JSON."
        else:
            task_dict = task_data # Should ideally be str per type hint, but safe fallback

        # Ensure project_id is set
        task_dict['project_id'] = pid
        
        # Call ImagicBox Client (Business Logic) - Async
        response = await imagicbox_client.create_task(data=task_dict)
        
        if response.get("code") == 0:
            return f"Success: Task created with ID {response.get('data', {}).get('task_id')}"
        else:
            return f"Failed: {response.get('message')}"
            
    except Exception as e:
        logger.error(f"Task creation failed: {e}")
        return f"Error preparing task creation: {str(e)}"
