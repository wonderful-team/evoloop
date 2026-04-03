import logging
from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.core.context.manager import ContextManager
from app.core.memory import MemoryContainer, MemoryConfig
from app.core.monitoring.ui_actions import require_project_for_tool
from app.core.tools import evoloop_tool
from app.utils import ProjectManagementFormatter

logger = logging.getLogger(__name__)


# Note: write_document and edit_document have been removed.
# Use write_file and edit_file from files module instead.
# They provide the same functionality with better path safety.


@evoloop_tool(
    is_pollable=True,
    summary_template="database_logger.tool_summary.consult_architecture"
)
async def consult_architecture(path: str = ""):
    """
    [ARCHITECT MODE] Consult the system's architectural documentation for a specific directory/module.
    Returns the module's role, sub-modules, and dependencies.
    Use this BEFORE refactoring or adding complex features to understand the ecosystem.

    Args:
        path: The relative path of the directory to inspect (e.g., "backend/app/core"). Defaults to root ("").
    """
    # Resolve project ID - allow temp project request in global mode
    pid = ContextManager.resolve_project_id(allow_global=False, request_temp=True)

    # If in global mode (pid=0), request project via HITL
    if pid == 0:
        result = await require_project_for_tool(
            tool_name="consult_architecture",
            tool_category="architecture",
            prompt="Please select a project to consult architecture:"
        )
        if isinstance(result, str):
            return result  # User cancelled
        pid = result

    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    try:
        manager = container.memory_manager
        info = await manager.graph.get_directory_info(pid, path)

        try:
            return ProjectManagementFormatter.architecture_summary(info)
        except Exception as e:
            logger.error(f"Failed to render architecture report: {e}")
            return f"Architecture info for {path}"
    finally:
        await container.shutdown()
