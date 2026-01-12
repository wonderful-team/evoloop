import os
import shutil
from typing import Literal

from langchain_core.runnables import RunnableConfig

from app.core.tools import get_working_directory
from app.utils.file import resolve_path

from .utils import resolve_and_validate_path


async def handle_filesystem(
    action: Literal['delete', 'move', 'create_directory'],
    path: str,
    content: str | None = None, # Used as destination for move
    config: RunnableConfig | None = None
) -> str:
    root = get_working_directory(config)

    try:
        target_path = resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if action == 'create_directory':
        try:
            os.makedirs(target_path, exist_ok=True)
            return f"Successfully created directory: {path}"
        except Exception as e:
            return f"Error creating directory: {e}"

    elif action == 'delete':
        if not os.path.exists(target_path):
            return f"Error: Path not found: {path}"
        try:
            if os.path.isdir(target_path):
                shutil.rmtree(target_path)
                return f"Successfully deleted directory: {path}"
            else:
                os.remove(target_path)
                return f"Successfully deleted file: {path}"
        except Exception as e:
            return f"Error deleting path: {e}"

    elif action == 'move':
        # content is treated as destination path here
        if not content: return "Error: 'content' (destination path) required for move action."

        dest_path = resolve_path(content, base_path=root)
        if not dest_path: return f"Error: Could not resolve destination: {content}"

        # Security Check for Destination
        if not str(dest_path).startswith(str(root)):
             return f"Error: Security Violation. Destination '{content}' is outside working directory."

        if not os.path.exists(target_path):
            return f"Error: Source path not found: {path}"

        try:
            shutil.move(target_path, dest_path)
            return f"Successfully moved '{path}' to '{content}'"
        except Exception as e:
            return f"Error moving path: {e}"

    return f"Error: Unknown filesystem action {action}"
