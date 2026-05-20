"""
Git-based knowledge harvesting tools.
"""
import os

from app.constants import DEFAULT_PROJECT_ID
from app.core.context.manager import ContextManager
from app.core.tools import evoloop_tool
from app.i18n.service import i18n


@evoloop_tool(summary_template="evoloop.tool_summary.auto_harvest_from_git")
async def auto_harvest_from_git():
    """
    Analyze uncommitted changes (working directory) to extract and save new Knowledge Concepts.
    Now offloaded to a background Celery task to prevent blocking the agent execution.
    """
    from app.core.engine.tasks import git_harvest_task

    ctx = ContextManager.current()
    project_id = ctx.project_id if ctx.project_id is not None else DEFAULT_PROJECT_ID
    cwd = ctx.working_directory or os.getcwd()

    # 0. Check if Git repo exists (Fast check)
    git_dir = os.path.join(cwd, ".git")
    if not os.path.exists(git_dir):
        return i18n.get("domain_tools.learner.no_git")

    # Dispatch to Celery
    git_harvest_task.delay(cwd, project_id)

    return "Knowledge harvesting initiated in background. I will continue learning from your changes."
