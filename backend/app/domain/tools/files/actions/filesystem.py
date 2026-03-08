import os
import shutil
from typing import Literal

from langchain_core.runnables import RunnableConfig

from app.core.tools import get_working_directory
from app.i18n.service import i18n
from app.utils.file import resolve_path

from .utils import resolve_and_validate_path


async def handle_filesystem(
    action: Literal["delete", "move", "create_directory"],
    path: str,
    content: str | None = None,  # Used as destination for move
    config: RunnableConfig | None = None,
) -> str:
    root = get_working_directory(config)

    try:
        target_path = resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if action == "create_directory":
        try:
            os.makedirs(target_path, exist_ok=True)
            return i18n.get("domain_tools.files.fs_create_dir_success", path=path)
        except Exception as e:
            return i18n.get("domain_tools.files.fs_create_dir_error", error=str(e))

    elif action == "delete":
        if not os.path.exists(target_path):
            return i18n.get("domain_tools.files.fs_not_found", path=path)
        try:
            if os.path.isdir(target_path):
                shutil.rmtree(target_path)
                return i18n.get("domain_tools.files.fs_delete_dir_success", path=path)
            else:
                os.remove(target_path)
                return i18n.get("domain_tools.files.fs_delete_file_success", path=path)
        except Exception as e:
            return i18n.get("domain_tools.files.fs_delete_error", error=str(e))

    elif action == "move":
        # content is treated as destination path here
        if not content:
            return i18n.get("domain_tools.files.fs_move_content_required")

        dest_path = resolve_path(content, base_path=root)
        if not dest_path:
            return i18n.get("domain_tools.files.fs_move_resolve_error", path=content)

        # Security Check for Destination
        if not str(dest_path).startswith(str(root)):
            return i18n.get("domain_tools.files.fs_move_security_error", path=content)

        if not os.path.exists(target_path):
            return i18n.get("domain_tools.files.fs_move_src_not_found", path=path)

        try:
            shutil.move(target_path, dest_path)
            return i18n.get("domain_tools.files.fs_move_success", src=path, dest=content)
        except Exception as e:
            return i18n.get("domain_tools.files.fs_move_error", error=str(e))

    return i18n.get("domain_tools.files.fs_unknown_action", action=action)
