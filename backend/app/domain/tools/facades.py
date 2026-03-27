import logging
import os
from typing import Annotated, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import InjectedToolArg

from app.constants import ALLOWED_DOC_EXTENSIONS
from app.core.context.manager import ContextManager
from app.core.memory import memory_manager
from app.core.monitoring.ui_actions import require_project_for_tool
from app.core.tools import evoloop_tool, get_working_directory
from app.domain.tools.files import edit_file
from app.utils import ProjectManagementFormatter
from app.utils.file import write_file_contents

logger = logging.getLogger(__name__)


@evoloop_tool(
    is_state_mutating=True,
    summary_template="database_logger.tool_summary.write_file",
    affected_path_keys=["path"],
    name_map={"zh": "写入文档", "en": "Write Document"}
)
async def write_document(path: str, content: str, config: Annotated[RunnableConfig, InjectedToolArg] = None) -> str:
    """
    [DOCS-ONLY] Write documentation files (.md, .txt, .json, .yaml, .csv) ONLY.
    """
    if not any(path.endswith(ext) for ext in ALLOWED_DOC_EXTENSIONS):
        return f"Error: Permission Denied. You may only write to {ALLOWED_DOC_EXTENSIONS}. For code changes, route to Coder."

    root = get_working_directory(config)
    target_path = os.path.abspath(os.path.join(root, path))

    write_file_contents(content, target_path)
    return f"Successfully wrote documentation to {path}"


@evoloop_tool(
    is_state_mutating=True,
    summary_template="database_logger.tool_summary.edit_file",
    affected_path_keys=["path"],
    name_map={"zh": "编辑文档", "en": "Edit Document"}
)
async def edit_document(
    path: str,
    target: str,
    replacement: str,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    """
    [DOCS-ONLY] Edit documentation files (.md, .txt, .json, .yaml, .csv) ONLY.
    """
    if not any(path.endswith(ext) for ext in ALLOWED_DOC_EXTENSIONS):
        return f"Error: Permission Denied. You may only edit {ALLOWED_DOC_EXTENSIONS}. For code changes, route to Coder."

    # Reuse generic edit tool logic or implement simple replace
    return await edit_file.ainvoke(
        {"path": path, "target": target, "replacement": replacement}, config=config
    )


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

    info = await memory_manager.graph.get_directory_info(pid, path)

    try:
        return ProjectManagementFormatter.architecture_summary(info)
    except Exception as e:
        logger.error(f"Failed to render architecture report: {e}")
        return f"Architecture info for {path}"
