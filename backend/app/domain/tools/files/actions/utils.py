
from langchain_core.runnables import RunnableConfig

from app.i18n.service import i18n
from app.core.tools import get_working_directory
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
    target_path = resolve_path(path, base_path=root)

    if not target_path: # Could not resolve
        raise ValueError(i18n.get("prompts.domain_tools.files.resolve_error", path=path))

    # Security Check: Prevent breaking out of working directory
    if not str(target_path).startswith(str(root)):
        raise ValueError(i18n.get("prompts.domain_tools.files.security_violation", path=path, root=root))

    return target_path
