import json
import logging

from langchain_core.tools import tool

from app.infrastructure.external.evocloud import evocloud_client
from app.logging import get_context

logger = logging.getLogger(__name__)


@tool
async def create_project_task(project_id: int | None = None, task_data: str = "") -> str:
    """
    Create a task in the remote project management system via EvoCloud.

    Args:
        project_id (int): The ID of the project to add the task to. Optional.
        task_data (str): JSON string representation of the task data (title, desc, priority, etc.).
    """
    pid = project_id or get_context().get("project_id", 1)

    try:
        # Parse task data if it's a string
        if isinstance(task_data, str):
            try:
                task_dict = json.loads(task_data)
            except json.JSONDecodeError:
                return "Error: task_data is not valid JSON."
        else:
            task_dict = task_data  # Should ideally be str per type hint, but safe fallback

        # Ensure project_id is set
        task_dict["project_id"] = pid

        # Call EvoCloud Client (Business Logic) - Async
        response = await evocloud_client.create_task(data=task_dict)

        if response.get("code") == 0:
            return f"Success: Task created with ID {response.get('data', {}).get('task_id')}"
        else:
            return f"Failed: {response.get('message')}"

    except Exception as e:
        logger.error(f"Task creation failed: {e}")
        return f"Error preparing task creation: {str(e)}"
