import logging
import os
import sqlite3

from app.core.context.manager import ContextManager
from app.core.file import ensure_local_path, read_file, resolve_path
from app.core.file.document_reader import document_reader_service
from app.core.file.tools.formatting import format_file_content, format_spreadsheet
from app.core.tools import evoloop_tool
from app.domain.tools.constants import (
    DOCX_HEADINGS_PREVIEW_LIMIT,
    MAX_PAGES,
    MAX_ROWS_PER_SHEET,
)
from app.domain.tools.schemas import (
    DocxHeading,
    DocxInspectionResult,
    ExcelInspectionResult,
    ExcelSheetInfo,
    PdfInspectionResult,
)
from app.utils.controller_response import ControllerResponse
from app.utils.detect import detect_language
from app.utils.template import render_template

try:
    import docx
    import mammoth
    import pandas as pd
    from markdownify import markdownify as md
    from pypdf import PdfReader
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Helper logic moved to app.core.file
# _ensure_local_path -> ensure_local_path
# _resolve_project_path -> resolve_path (with context awareness handled below or in util if passed)


def _resolve_project_path(file_path: str) -> str:
    """Wrapper for utils.resolve_path to inject project context default"""
    if file_path.startswith(("http://", "https://")):
        return file_path

    ctx = ContextManager.current()
    root = ctx.working_directory or os.getcwd()
    return resolve_path(file_path, base_path=root) or file_path


@evoloop_tool(
    summary_template="evoloop.tool_summary.query_excel_sql",
    affected_path_keys=["file_path"],
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
    from app.core.file.tools.utils import resolve_and_validate_path

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


async def read_document(
    file_path: str, start_page: int | None = None, end_page: int | None = None
) -> str:
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

        content = await document_reader_service.read_document(
            real_path, start_page, end_page
        )

        # Wrap in file header if not already
        filename = os.path.basename(real_path)
        lang = detect_language(real_path) or "text"

        if content.strip().startswith("# "):  # Already has a header
            return content

        return format_file_content(filename, content, lang)

    except Exception as e:
        logger.exception(f"Read failed: {e}")
        return ControllerResponse.error(
            f"Error reading file {file_path}", details=str(e)
        )


# --- core Logic Helpers ---


def _list_directory(real_path: str) -> str:
    """Returns a standardized formatted listing of the directory using unified traverser."""
    try:
        from app.core.file import FileTraverser

        entries = FileTraverser.list_entries(real_path)
        visible_entries = [e for e in entries if not e.name.startswith(".")]

        formatted_items = []
        for e in visible_entries:
            if e.is_dir():
                formatted_items.append(f"{e.name}/")
            else:
                formatted_items.append(e.name)

        listing_str = "\n".join(formatted_items[:50]) + (
            "\n... (truncated)" if len(formatted_items) > 50 else ""
        )
        return (
            f"SYSTEM NOTICE: Target is a directory\n"
            f"Path: {os.path.basename(real_path)}/\n"
            f"The path you requested is a directory, not a file. I have listed its contents below for your convenience:\n\n"
            f"{listing_str}"
        )
    except Exception as e:
        return f"Error listing directory: {e}"


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
        headings=(
            headings[:DOCX_HEADINGS_PREVIEW_LIMIT]
            if len(headings) > DOCX_HEADINGS_PREVIEW_LIMIT
            else headings
        ),
    )


def _inspect_pdf(path: str) -> PdfInspectionResult:
    reader = PdfReader(path)
    return PdfInspectionResult(pages=len(reader.pages), metadata=reader.metadata)


def _read_pdf(path: str, start: int | None, end: int | None) -> str:
    reader = PdfReader(path)
    total_pages = len(reader.pages)

    start_idx = (start - 1) if start else 0

    is_truncated = False
    if end is None:
        end_idx = min(start_idx + MAX_PAGES, total_pages)
        if total_pages > end_idx:
            is_truncated = True
    else:
        end_idx = min(total_pages, end)

    try:
        content_blocks = []
        for i in range(start_idx, end_idx):
            content_blocks.append(
                {"title": f"Page {i + 1}", "content": reader.pages[i].extract_text()}
            )

        footer_msg = ""
        if is_truncated:
            footer_msg = f"\n\n... (PDF truncated to first {MAX_PAGES} pages)\n"
            footer_msg += f"Tip: Use `read_file(path='...', start_line={end_idx + 1})` to read more pages."

        return (
            render_template(
                "domain/project/document_content.prompt.j2",
                type="document",
                filename=os.path.basename(path),
                metadata=reader.metadata,
                page_info=f"Pages: {start_idx + 1} to {end_idx} (Total {total_pages})",
                content_blocks=content_blocks,
            )
            + footer_msg
        )
    except Exception as e:
        logger.exception(f"Failed to render Document template for PDF: {e}")
        # Fallback to simple template
        content_blocks = []
        for i in range(start_idx, end_idx):
            content_blocks.append(
                {"title": f"Page {i + 1}", "content": reader.pages[i].extract_text()}
            )
        return render_template(
            "domain/project/document_content.prompt.j2",
            type="document",
            filename=os.path.basename(path),
            metadata=reader.metadata,
            page_info=f"Pages: {start_idx + 1} to {end_idx} (Total {total_pages})",
            content_blocks=content_blocks,
        )


def _read_docx(path: str) -> str:
    """Standardized DOCX reading using unified IO (indirectly via mammoth)."""
    # mammoth requires a file-like object in binary mode
    with open(path, "rb") as docx_file:
        result = mammoth.convert_to_markdown(docx_file)
        return format_file_content(
            os.path.basename(path), result.value, lang="markdown"
        )


def _read_excel(path: str) -> str:
    xl = pd.ExcelFile(path)
    sheet_names = xl.sheet_names  # Get sheet names once
    try:
        content_blocks = []
        for sheet_name in sheet_names:
            # Read only first N rows for preview
            df = pd.read_excel(
                path, sheet_name=sheet_name, nrows=MAX_ROWS_PER_SHEET + 1
            )

            is_truncated = len(df) > MAX_ROWS_PER_SHEET
            if is_truncated:
                df = df.head(MAX_ROWS_PER_SHEET)

            content = df.to_markdown(index=False) if not df.empty else "*Empty Sheet*"

            if is_truncated:
                content += f"\n\n... (Sheet '{sheet_name}' truncated to first {MAX_ROWS_PER_SHEET} rows)"
                content += "\nTip: This spreadsheet is large. Use `query_excel_sql` to perform precise queries on the data."

            content_blocks.append({"title": f"Sheet: {sheet_name}", "content": content})

        return render_template(
            "domain/project/document_content.prompt.j2",
            type="spreadsheet",
            filename=os.path.basename(path),
            content_blocks=content_blocks,
        )
    except Exception as e:
        logger.exception(f"Failed to render Spreadsheet template: {e}")
        # Fallback to spreadsheet formatter
        sheets = []
        for sheet_name in sheet_names:
            df = pd.read_excel(path, sheet_name=sheet_name, nrows=MAX_ROWS_PER_SHEET)
            sheets.append(
                {
                    "name": sheet_name,
                    "content": df.to_markdown(index=False)
                    if not df.empty
                    else "*Empty Sheet*",
                    "is_empty": df.empty,
                }
            )
        return format_spreadsheet(os.path.basename(path), sheets)


def _read_html(path: str) -> str:
    """Standardized HTML reading using unified core IO."""
    result = read_file(path)
    return format_file_content(
        os.path.basename(path), md(result.content), lang="markdown"
    )
