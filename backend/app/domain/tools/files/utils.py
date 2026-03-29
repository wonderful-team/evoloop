from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.context import ContextManager
from app.core.tools import get_working_directory
from app.i18n.service import i18n
from app.utils.file import resolve_path


async def resolve_and_validate_path(path: str, config: RunnableConfig | None = None) -> str:
    """
    Resolve path and perform security check.
    
    File operations do NOT require a project - they only need a safe base path.
    In global mode, uses WORKSPACE_ROOT as the base directory.
    Raises ValueError on security violation or resolution failure.
    """
    # Handle Agent Hallucinations (treating system root dependencies)
    if path.strip() == "/" or path.strip() == "":
        path = "."

    root = get_working_directory(config)

    # In global mode (project_id is 0 or None, and root is current dir),
    # use WORKSPACE_ROOT as the base directory for file operations.
    # File operations don't require a project - they just need a safe workspace.
    ctx = ContextManager.current()
    if ctx.project_id == 0 or (ctx.project_id is None and root == "."):
        from app.infrastructure.config.service import SystemConfigService

        db_workspace_root = SystemConfigService.get_value("WORKSPACE_ROOT")
        workspace_root = db_workspace_root if db_workspace_root else settings.WORKSPACE_ROOT

        if workspace_root:
            root = workspace_root

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
