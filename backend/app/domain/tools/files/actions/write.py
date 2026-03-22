from langchain_core.runnables import RunnableConfig

from app.i18n.service import i18n
from app.utils.file import write_file_contents as utils_write_file

from .utils import resolve_and_validate_path


async def handle_write(
    action: str,
    path: str,
    content: str | None = None,
    config: RunnableConfig | None = None,
) -> str:
    if content is None:
        return i18n.get("domain_tools.files.write_content_required", action=action)

    try:
        target_path = await resolve_and_validate_path(path, config)
        utils_write_file(content, target_path)
        return i18n.get("domain_tools.files.write_success", path=path)
    except Exception as e:
        return i18n.get("domain_tools.files.write_error", error=str(e))
