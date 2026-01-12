
from langchain_core.runnables import RunnableConfig

from app.utils.file import write_file_contents as utils_write_file

from .utils import resolve_and_validate_path


async def handle_write(action: str, path: str, content: str | None = None, config: RunnableConfig | None = None) -> str:
    if content is None: return f"Error: 'content' required for {action} action."

    try:
        target_path = resolve_and_validate_path(path, config)
        utils_write_file(content, target_path)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {e}"
