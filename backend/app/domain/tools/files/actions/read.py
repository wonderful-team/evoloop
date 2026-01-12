import os

from langchain_core.runnables import RunnableConfig

from app.domain.tools.document_reader import read_document
from app.utils.file import read_file_content as utils_read_file

from .utils import resolve_and_validate_path


async def handle_read(path: str, start_line: int | None = None, end_line: int | None = None, config: RunnableConfig | None = None) -> str:
    try:
        target_path = resolve_and_validate_path(path, config)
    except ValueError as e:
        return str(e)

    # Smart routing: if it looks like a doc, use read_document logic
    if path.lower().endswith(('.pdf', '.docx', '.doc')):
        return await read_document.ainvoke({"file_path": path}, config=config)

    if not os.path.exists(target_path):
         # Smart Error Handling
         parent_dir = os.path.dirname(target_path)
         if os.path.exists(parent_dir):
             try:
                 siblings = os.listdir(parent_dir)
                 siblings_str = ", ".join(siblings[:20])
                 return f"Error: File '{path}' not found. Did you mean one of these in the same directory? [{siblings_str}]"
             except:
                 pass
         return f"Error: File not found: {path}"

    try:
        file_content, _ = utils_read_file(target_path, start_line, end_line)
        return file_content
    except Exception as e:
        return f"Error reading file: {e}"
