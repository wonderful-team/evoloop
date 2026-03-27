from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.context import ContextManager
from app.core.tools import get_working_directory
from app.i18n.service import i18n
from app.utils.file import resolve_path


async def resolve_and_validate_path(path: str, config: RunnableConfig | None = None) -> str:
    """
    Resolve path and perform security check.
    In global mode, prompts user to select/create a project via HITL.
    Raises ValueError on security violation, resolution failure, or user cancellation.
    """
    # Handle Agent Hallucinations (treating system root dependencies)
    if path.strip() == "/" or path.strip() == "":
        path = "."

    root = get_working_directory(config)

    # Global Mode Check: If working directory is not set, prompt user to select/create project
    ctx = ContextManager.current()
    if ctx.project_id == 0 or (ctx.project_id is None and root == "."):
        from app.infrastructure.config.service import SystemConfigService
        from app.core.monitoring.ui_actions import require_project_for_tool

        db_workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
        workspace_root = db_workspace_root if db_workspace_root else settings.WORKSPACE_ROOT

        if root == "." or root == workspace_root:
            # Global mode detected - request project via HITL
            result = await require_project_for_tool(
                tool_name="file_operation",
                tool_category="file_operation",
                prompt="📁 **文件操作需要项目**\n\n当前处于全局模式，文件操作需要在特定项目中进行。请选择一个项目继续："
            )

            if isinstance(result, str):
                # User cancelled or error
                raise ValueError(f"❌ 文件操作已取消：{result}")

            # Project selected via HITL (temp project is set automatically)
            # Re-resolve working directory with new project context
            root = get_working_directory(config)

    target_path = resolve_path(path, base_path=root)

    if not target_path:  # Could not resolve
        raise ValueError(i18n.get("domain_tools.files.resolve_error", path=path))

    # Security Check: Prevent breaking out of working directory
    is_safe = str(target_path).startswith(str(root))

    if not is_safe:
        # Optional: Allow whitelisted system paths (e.g., /tmp/dataset for testing)
        for prefix in settings.ALLOWED_PATH_PREFIXES:
            if str(target_path).startswith(prefix):
                is_safe = True
                break

    if not is_safe:
        raise ValueError(i18n.get("domain_tools.files.security_violation", path=path, root=root))

    return target_path
