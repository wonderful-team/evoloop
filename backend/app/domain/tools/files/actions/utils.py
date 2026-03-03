from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.context import ContextManager
from app.core.tools import get_working_directory
from app.i18n.service import i18n
from app.utils.file import resolve_path


def resolve_and_validate_path(path: str, config: RunnableConfig | None = None) -> str:
    """
    Resolve path and perform security check.
    Raises ValueError on security violation or resolution failure.
    """
    # Handle Agent Hallucinations (treating system root dependencies)
    if path.strip() == "/" or path.strip() == "":
        path = "."

    root = get_working_directory(config)

    # Global Mode Check: If working directory is not set (fallback to cwd/workspace_root),
    # we should warn about potential incorrect file operations
    # Note: This is a safety check - in global mode, file operations may not work as expected
    ctx = ContextManager.current()
    if ctx.project_id == 0 or (ctx.project_id is None and root == "."):
        # Global mode detected - file operations are restricted
        from app.infrastructure.config.service import SystemConfigService

        db_workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
        workspace_root = db_workspace_root if db_workspace_root else settings.WORKSPACE_ROOT
        if root == "." or root == workspace_root:
            raise ValueError(
                f"File operations are not available in global mode. "
                f"Please switch to a specific project to use file tools."
            )

    target_path = resolve_path(path, base_path=root)

    if not target_path:  # Could not resolve
        raise ValueError(i18n.get("prompts.domain_tools.files.resolve_error", path=path))

    # Security Check: Prevent breaking out of working directory
    if not str(target_path).startswith(str(root)):
        raise ValueError(i18n.get("prompts.domain_tools.files.security_violation", path=path, root=root))

    return target_path
