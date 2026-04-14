import logging
import os
import sqlite3

from pydantic import BaseModel

from app.core.context.manager import ContextManager
from app.core.file.document_reader import document_reader_service
from app.core.tools import evoloop_tool
from app.infrastructure.pydantic_base import DynamicBaseModel
from app.utils import ContentFormatter, ControllerResponse, render_template
from app.utils import json as json_utils
from app.utils.detect import detect_language
from app.utils.file import ensure_local_path, read_file_content, resolve_path

try:
    import docx
    import mammoth
    import pandas as pd
    from markdownify import markdownify as md
    from pypdf import PdfReader
except ImportError:
    pass

logger = logging.getLogger(__name__)


# Helper logic moved to app.utils.file
# _ensure_local_path -> ensure_local_path
# _resolve_project_path -> resolve_path (with context awareness handled below or in util if passed)


class DocxHeading(BaseModel):
    style: str
    text: str


class ExcelSheetInfo(DynamicBaseModel):
    columns: list[str]
    preview: list[dict]


class ExcelInspectionResult(DynamicBaseModel):
    sheets: list[str]
    details: dict[str, ExcelSheetInfo]


class DocxInspectionResult(DynamicBaseModel):
    headings_count: int
    headings: list[DocxHeading]


class PdfInspectionResult(DynamicBaseModel):
    pages: int
    metadata: dict | None = None


def _resolve_project_path(file_path: str) -> str:
    """Wrapper for utils.resolve_path to inject project context default"""
    if file_path.startswith(("http://", "https://")):
        return file_path

    ctx = ContextManager.current()
    root = ctx.working_directory or os.getcwd()
    return resolve_path(file_path, base_path=root) or file_path


def inspect_document(file_path: str) -> str:
    """
    [INTERNAL USE ONLY - Not exposed as Agent tool]
    Inspect a document to get its metadata and structure without reading the full content.
    Useful for planning how to read large files.

    Args:
        file_path (str): Absolute path to the file (must be resolved and validated by caller).

    Returns:
        str: JSON formatted metadata.
    """
    try:
        # Note: file_path should already be resolved and validated by the caller
        real_path = ensure_local_path(file_path)
    except Exception as e:
        return json_utils.dumps({"error": str(e)})

    if not os.path.exists(real_path):
        return json_utils.dumps({"error": f"File not found: {real_path}"})

    _ext = os.path.splitext(real_path)[1].lower()
    metadata = {
        "file_path": file_path,
        "local_path": real_path,
        "type": _ext,
        "size_bytes": os.path.getsize(real_path),
    }

    try:
        if _ext in [".xlsx", ".xls"]:
            metadata.update(_inspect_excel(real_path))
        elif _ext in [".docx", ".doc"]:
            metadata.update(_inspect_docx(real_path))
        elif _ext == ".pdf":
            metadata.update(_inspect_pdf(real_path))
        else:
            metadata["info"] = "Standard text file"

        return json_utils.dumps(metadata, indent=2)
    except Exception as e:
        logger.error(f"Inspection failed: {e}")
        return json_utils.dumps({"error": str(e)})


@evoloop_tool(
    is_pollable=True,
    name_map={"zh": "查询Excel", "en": "Query Excel SQL"}
)
async def query_excel_sql(file_path: str, sql_query: str) -> str:
    """
    Execute a SQL query on an Excel file using an in-memory SQLite database.
    
    This is designed for efficiently querying large Excel files (>500MB) without loading
    the entire file into context. The Excel data is loaded into a temporary SQLite
    database for fast SQL querying.

    The table name is strictly 'data'. If the Excel has multiple sheets,
    this tool currently loads the first sheet by default.

    Args:
        file_path: Path to the Excel file (.xlsx, .xls). **REQUIRED**
        sql_query: SQL query string. **REQUIRED**
                 Examples: "SELECT * FROM data LIMIT 5"
                          "SELECT col1, SUM(col2) FROM data GROUP BY col1"
                          "SELECT * FROM data WHERE age > 18"

    Returns:
        JSON string of the query results.
    
    Example:
        query_excel_sql(file_path="sales_data.xlsx", sql_query="SELECT * FROM data WHERE revenue > 10000")
    """
    # Import here to avoid circular imports
    from app.domain.tools.files.utils import resolve_and_validate_path
    
    try:
        # Resolve and validate path for security
        real_path = await resolve_and_validate_path(file_path, None)
    except ValueError as e:
        return f"Error: {str(e)}"

    if not os.path.exists(real_path):
        return f"Error: File not found {real_path}"

    try:
        # Load Excel to DataFrame
        # Optimization: If query is simple, we might not need to load everything,
        # but for V1 we load the sheet into memory.
        df = pd.read_excel(real_path)  # Loads first sheet by default

        # Clean column names to be SQL friendly (optional but good practice)
        # Replacing spaces with underscores
        df.columns = [str(c).strip().replace(" ", "_") for c in df.columns]

        # Create in-memory SQLite DB
        conn = sqlite3.connect(":memory:")
        df.to_sql("data", conn, index=False, if_exists="replace")

        # Execute Query
        result_df = pd.read_sql_query(sql_query, conn)
        conn.close()

        result = result_df.to_json(orient="records", force_ascii=False)
        return result if result is not None else "[]"

    except Exception as e:
        return f"SQL Execution Error: {str(e)}"


async def read_document(file_path: str, start_page: int | None = None, end_page: int | None = None) -> str:
    """
    [INTERNAL USE ONLY - Not exposed as Agent tool]
    Read and parse content from various document formats (PDF, DOCX, XLSX, MD, TXT, HTML, PY, JS, IMG, etc.).
    Returns the content converted to Markdown format.
    
    This function is called internally by read_file for special document formats.
    It should NOT be called directly by the Agent.

    Args:
        file_path (str): Path to the file (must be resolved and validated by caller).
        start_page (int, optional): Start page for PDF (1-based).
        end_page (int, optional): End page for PDF (1-based).
    """
    try:
        # Note: file_path should already be resolved and validated by the caller (read_file)
        real_path = ensure_local_path(file_path)

        if os.path.isdir(real_path):
            return _list_directory(real_path)

        content = await document_reader_service.read_document(real_path, start_page, end_page)

        # Wrap in file header if not already
        filename = os.path.basename(real_path)
        lang = detect_language(real_path) or "text"

        if content.strip().startswith("# "): # Already has a header
            return content

        return ContentFormatter.file_content(filename, content, lang)

    except Exception as e:
        logger.error(f"Read failed: {e}")
        return ControllerResponse.error(f"Error reading file {file_path}", details=str(e))


# --- core Logic Helpers ---


def _resolve_and_validate(file_path: str) -> tuple[str | None, str | None]:
    """
    Resolves the path and checks existence.
    Returns (real_path, None) if successful.
    Returns (None, error_message) if failed (with fuzzy suggestion).
    """
    try:
        resolved_path = _resolve_project_path(file_path)
        real_path = ensure_local_path(resolved_path)
    except Exception as e:
        return None, f"Error resolving path: {str(e)}"

    if os.path.exists(real_path):
        return real_path, None

    # Smart Fuzzy Check for Typo/Case sensitivity
    dir_name = os.path.dirname(real_path)
    base_name = os.path.basename(real_path)
    suggestion = ""
    parent_listing_info = ""

    if os.path.exists(dir_name) and os.path.isdir(dir_name):
        try:
            candidates = sorted(os.listdir(dir_name))
            visible_candidates = [c for c in candidates if not c.startswith(".")]

            # 1. Exact case-insensitive match
            for c in candidates:
                if c.lower() == base_name.lower():
                    suggestion = f" (Did you mean '{c}'?)"
                    break

            # 2. Provide context (Parent Listing)
            list_str = ", ".join(visible_candidates[:20])
            if len(visible_candidates) > 20:
                list_str += ", ..."

            parent_listing_info = (
                f"\n\nCONTEXT HELP: The directory '{os.path.basename(dir_name)}/' exists and contains these files:\n"
                f"[{list_str}]\n"
                f"Please check the spelling or choose an existing file from the list."
            )
        except Exception:
            pass

    return None, f"Error: File not found: {real_path}{suggestion} (Resolved from {file_path}){parent_listing_info}"


def _list_directory(real_path: str) -> str:
    """Returns a formatted listing of the directory."""
    try:
        items = sorted(os.listdir(real_path))
        visible_items = [i for i in items if not i.startswith(".")]
        formatted_items = []
        for item in visible_items:
            if os.path.isdir(os.path.join(real_path, item)):
                formatted_items.append(f"{item}/")
            else:
                formatted_items.append(item)

        listing_str = "\n".join(formatted_items[:50]) + ("\n... (truncated)" if len(formatted_items) > 50 else "")
        return (
            f"SYSTEM NOTICE: Target is a directory\n"
            f"Path: {os.path.basename(real_path)}/\n"
            f"The path you requested is a directory, not a file. I have listed its contents below for your convenience:\n\n"
            f"{listing_str}"
        )
    except Exception as e:
        return f"Error listing directory: {e}"


def _read_file_content(real_path: str, start: int | None, end: int | None) -> str:
    """Dispatches reading logic based on file extension."""
    _ext = os.path.splitext(real_path)[1].lower()

    if _ext in [".xlsx", ".xls"]:
        return _read_excel(real_path)
    elif _ext in [".docx", ".doc"]:
        return _read_docx(real_path)
    elif _ext == ".pdf":
        return _read_pdf(real_path, start, end)
    elif _ext == ".html":
        return _read_html(real_path)
    else:
        # Code/Text Fallback. Using utils reading.
        content, _, _ = read_file_content(real_path)
        lang = detect_language(real_path)
        return _wrap_code_block(real_path, content, lang)


def _wrap_code_block(path: str, content: str, lang: str) -> str:
    """Reads a text file and returns it wrapped in a markdown code block."""
    filename = os.path.basename(path)
    return ContentFormatter.file_content(filename, content, lang)


# --- Inspection Helpers ---


def _inspect_excel(path: str) -> ExcelInspectionResult:
    xl = pd.ExcelFile(path)
    sheets_info: dict[str, ExcelSheetInfo] = {}
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet, nrows=5)  # Peek top 5
        sheets_info[sheet] = ExcelSheetInfo(
            columns=list(df.columns),
            preview=df.head(2).to_dict(orient="records"),
        )
    return ExcelInspectionResult(sheets=list(xl.sheet_names), details=sheets_info)


def _inspect_docx(path: str) -> DocxInspectionResult:
    doc = docx.Document(path)
    headings: list[DocxHeading] = []
    for para in doc.paragraphs:
        if para.style and para.style.name and para.style.name.startswith("Heading"):
            headings.append(DocxHeading(style=para.style.name, text=para.text))

    return DocxInspectionResult(
        headings_count=len(headings),
        headings=headings[:20] if len(headings) > 20 else headings,
    )


def _inspect_pdf(path: str) -> PdfInspectionResult:
    reader = PdfReader(path)
    return PdfInspectionResult(pages=len(reader.pages), metadata=reader.metadata)


def _read_pdf(path: str, start: int | None, end: int | None) -> str:
    reader = PdfReader(path)
    total_pages = len(reader.pages)

    start_idx = (start - 1) if start else 0
    end_idx = end if end else total_pages
    start_idx = max(0, start_idx)
    end_idx = min(total_pages, end_idx)

    try:
        content_blocks = []
        for i in range(start_idx, end_idx):
            content_blocks.append({
                "title": f"Page {i+1}",
                "content": reader.pages[i].extract_text()
            })

        return render_template(
            "project/document_content.prompt.j2",
            type="document",
            filename=os.path.basename(path),
            metadata=reader.metadata,
            page_info=f"Pages: {start_idx+1} to {end_idx} (Total {total_pages})",
            content_blocks=content_blocks
        )
    except Exception as e:
        logger.error(f"Failed to render Document template for PDF: {e}")
        # Fallback to simple template
        content_blocks = []
        for i in range(start_idx, end_idx):
            content_blocks.append({
                "title": f"Page {i+1}",
                "content": reader.pages[i].extract_text()
            })
        return render_template(
            "project/document_content.prompt.j2",
            type="document",
            filename=os.path.basename(path),
            metadata=reader.metadata,
            page_info=f"Pages: {start_idx+1} to {end_idx} (Total {total_pages})",
            content_blocks=content_blocks
        )


def _read_docx(path: str) -> str:
    with open(path, "rb") as docx_file:
        result = mammoth.convert_to_markdown(docx_file)
        return ContentFormatter.file_content(os.path.basename(path), result.value, lang="markdown")


def _read_excel(path: str) -> str:
    xl = pd.ExcelFile(path)
    sheet_names = xl.sheet_names # Get sheet names once
    try:
        content_blocks = []
        for sheet_name in sheet_names:
            df = pd.read_excel(path, sheet_name=sheet_name)
            content_blocks.append({
                "title": f"Sheet: {sheet_name}",
                "content": df.to_markdown(index=False) if not df.empty else "*Empty Sheet*"
            })

        return render_template(
            "project/document_content.prompt.j2",
            type="spreadsheet",
            filename=os.path.basename(path),
            content_blocks=content_blocks
        )
    except Exception as e:
        logger.error(f"Failed to render Spreadsheet template: {e}")
        # Fallback to spreadsheet formatter
        sheets = []
        for sheet_name in sheet_names:
            df = pd.read_excel(path, sheet_name=sheet_name)
            sheets.append({
                "name": sheet_name,
                "content": df.to_markdown(index=False) if not df.empty else "*Empty Sheet*",
                "is_empty": df.empty
            })
        return ContentFormatter.spreadsheet(os.path.basename(path), sheets)


def _read_html(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        html_content = f.read()
    return ContentFormatter.file_content(os.path.basename(path), md(html_content), lang="markdown")
