import os

from langchain_core.runnables import RunnableConfig

from app.i18n.service import i18n
from app.utils.file import write_file_contents as utils_write_file

from .utils import resolve_and_validate_path


async def handle_edit(
    path: str,
    target: str | None = None,
    content: str | None = None,
    allow_multiple: bool = False,
    config: RunnableConfig | None = None,
) -> str:
    if not target and not content:
        return i18n.get("domain_tools.files.edit_args_required")

    # Safety Check: Target Uniqueness
    # Relaxed for single-line edits
    if len(target.strip()) < 3:
        return i18n.get("domain_tools.files.edit_target_short")

    try:
        target_path = resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    if not os.path.exists(target_path):
        return i18n.get("domain_tools.files.edit_not_found", path=path)

    try:
        with open(target_path, encoding="utf-8") as f:
            file_content = f.read()

        count = file_content.count(target)
        if count == 0:
            # Fall through to Fuzzy
            pass
        elif count > 1 and not allow_multiple:
            return i18n.get("domain_tools.files.edit_multiple_found", count=count)
        else:
            # Strict Success
            if allow_multiple:
                new_content = file_content.replace(target, content)
            else:
                new_content = file_content.replace(target, content, 1)

            utils_write_file(new_content, target_path)
            return i18n.get("domain_tools.files.edit_success", path=path)

        # 2. Try Fuzzy Fallback (Robust Edit Engine)
        from app.domain.tools.utils.editing.engine import EditEngine

        success, new_content, log = EditEngine.apply_replacement(
            file_content, target, content, replace_all=allow_multiple
        )
        if success:
            utils_write_file(new_content, target_path)
            return i18n.get("domain_tools.files.edit_success_log", path=path, log=log)

        return i18n.get("domain_tools.files.edit_fallback_failed", log=log)

    except Exception as e:
        return i18n.get("domain_tools.files.edit_error", error=str(e))
