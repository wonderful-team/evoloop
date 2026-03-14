import os

from langchain_core.runnables import RunnableConfig

from app.domain.tools.document_reader import read_document
from app.i18n.service import i18n
from app.utils.file import read_file_content as utils_read_file

from .utils import resolve_and_validate_path


async def handle_read(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    config: RunnableConfig | None = None,
) -> str:
    try:
        target_path = resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    # Smart routing: if it looks like a doc, use read_document logic
    if path.lower().endswith((".pdf", ".docx", ".doc", ".xlsx", ".xls")):
        return await read_document.ainvoke(
            {"file_path": path, "start_page": start_line, "end_page": end_line}, 
            config=config
        )

    if not os.path.exists(target_path):
        # Smart Error Handling
        parent_dir = os.path.dirname(target_path)
        if os.path.exists(parent_dir):
            try:
                siblings = os.listdir(parent_dir)
                siblings_info = []
                for s in siblings[:20]:
                    full_s = os.path.join(parent_dir, s)
                    if os.path.isdir(full_s):
                        siblings_info.append(f"{s}/")
                    else:
                        siblings_info.append(s)
                siblings_str = ", ".join(siblings_info)
                return i18n.get(
                    "domain_tools.files.read_not_found_suggest",
                    path=path,
                    siblings=siblings_str,
                )
            except Exception:
                pass
        return i18n.get("domain_tools.files.read_not_found", path=path)

    try:
        file_content, _ = utils_read_file(target_path, start_line, end_line)
        return file_content
    except Exception as e:
        return i18n.get("domain_tools.files.read_error", error=str(e))
