import logging
import os
import shutil
import sqlite3
import tempfile
import urllib.request
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from app.utils import json as json_utils

from langchain_core.tools import tool

from app.logging import get_context

from app.constants import EXTENSION_MAP
from app.utils.file import resolve_path, ensure_local_path, read_file_content
from app.utils.detect import detect_language

try:
    import pandas as pd
    import docx
    import mammoth
    from pypdf import PdfReader
    from markdownify import markdownify as md
except ImportError:
    pass

logger = logging.getLogger(__name__)


# Helper logic moved to app.utils.file
# _ensure_local_path -> ensure_local_path
# _resolve_project_path -> resolve_path (with context awareness handled below or in util if passed)

def _resolve_project_path(file_path: str) -> str:
    """Wrapper for utils.resolve_path to inject project context default"""
    if file_path.startswith(('http://', 'https://')):
        return file_path
    
    ctx = get_context()
    root = ctx.get("working_directory") or os.getcwd()
    return resolve_path(file_path, base_path=root) or file_path


def inspect_document(file_path: str) -> str:
    """
    Inspect a document to get its metadata and structure without reading the full content.
    Useful for planning how to read large files.
    
    Args:
        file_path (str): Absolute path to the file.
        
    Returns:
        str: JSON formatted metadata.
    """
    try:
        resolved_path = _resolve_project_path(file_path)
        real_path = ensure_local_path(resolved_path)
    except Exception as e:
        return json_utils.dumps({"error": str(e)})

    if not os.path.exists(real_path):
        return json_utils.dumps({"error": f"File not found: {real_path}"})

    _ext = os.path.splitext(real_path)[1].lower()
    metadata = {"file_path": file_path, "local_path": real_path, "type": _ext, "size_bytes": os.path.getsize(real_path)}

    try:
        if _ext in ['.xlsx', '.xls']:
            metadata.update(_inspect_excel(real_path))
        elif _ext in ['.docx', '.doc']:
            metadata.update(_inspect_docx(real_path))
        elif _ext == '.pdf':
            metadata.update(_inspect_pdf(real_path))
        else:
            metadata["info"] = "Standard text file"
            
        return json_utils.dumps(metadata, indent=2)
    except Exception as e:
        logger.error(f"Inspection failed: {e}")
        return json_utils.dumps({"error": str(e)})


def query_excel_sql(file_path: str, sql_query: str) -> str:
    """
    Execute a SQL query on an Excel file.
    The table name is strictly 'data'. If the Excel has multiple sheets, 
    this tool currently loads the first sheet by default unless specified otherwise 
    (Future: support sheet selection).
    
    Args:
        file_path: Path to Excel file or URL.
        sql_query: SQL query string (e.g., "SELECT * FROM data LIMIT 5", "SELECT col1, SUM(col2) FROM data GROUP BY col1").
        
    Returns:
        JSON string of the result.
    """
    try:
        resolved_path = _resolve_project_path(file_path)
        real_path = ensure_local_path(resolved_path)
    except Exception as e:
        return f"Error: {str(e)}"

    if not os.path.exists(real_path):
        return f"Error: File not found {real_path}"
    
    try:
        # Load Excel to DataFrame
        # Optimization: If query is simple, we might not need to load everything, 
        # but for V1 we load the sheet into memory.
        df = pd.read_excel(real_path) # Loads first sheet by default
        
        # Clean column names to be SQL friendly (optional but good practice)
        # Replacing spaces with underscores
        df.columns = [str(c).strip().replace(' ', '_') for c in df.columns]
        
        # Create in-memory SQLite DB
        conn = sqlite3.connect(':memory:')
        df.to_sql('data', conn, index=False, if_exists='replace')
        
        # Execute Query
        result_df = pd.read_sql_query(sql_query, conn)
        conn.close()
        
        return result_df.to_json(orient='records', force_ascii=False)
        
    except Exception as e:
        return f"SQL Execution Error: {str(e)}"


# Constants moved to app.constants

# --- Main Tool ---

@tool
def read_document(file_path: str, start_page: Optional[int] = None, end_page: Optional[int] = None) -> str:
    """
    Read and parse content from various document formats (PDF, DOCX, XLSX, MD, TXT, HTML, PY, JS, etc.).
    Returns the content converted to Markdown format.
    
    For code or text files, it returns a Markdown code block with specific language highlighting.
    For documents like PDF/Word, it returns formatted text.

    Args:
        file_path (str): Path to the file or URL.
        start_page (int, optional): Start page for PDF (1-based).
        end_page (int, optional): End page for PDF (1-based).
    """
    # 1. Resolve and Validate Path
    real_path, error_msg = _resolve_and_validate(file_path)
    if error_msg:
        return error_msg
        
    # 2. Handle Directory
    if os.path.isdir(real_path):
        return _list_directory(real_path)
        
    # 3. Read File Content
    try:
        return _read_file_content(real_path, start_page, end_page)
    except Exception as e:
        logger.error(f"Read failed: {e}")
        return f"Error reading file {os.path.basename(real_path)}: {str(e)}"


# --- core Logic Helpers ---

def _resolve_and_validate(file_path: str) -> Tuple[Optional[str], Optional[str]]:
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
            visible_candidates = [c for c in candidates if not c.startswith('.')]
            
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
        except: 
            pass
    
    return None, f"Error: File not found: {real_path}{suggestion} (Resolved from {file_path}){parent_listing_info}"


def _list_directory(real_path: str) -> str:
    """Returns a formatted listing of the directory."""
    try:
        items = sorted(os.listdir(real_path))
        visible_items = [i for i in items if not i.startswith('.')]
        formatted_items = []
        for item in visible_items:
            if os.path.isdir(os.path.join(real_path, item)):
                formatted_items.append(f"{item}/")
            else:
                formatted_items.append(item)
        
        listing_str = "\n".join(formatted_items[:50]) + ("\n... (truncated)" if len(formatted_items) > 50 else "")
        return (
            f"### SYSTEM NOTICE: Target is a directory ###\n"
            f"Path: {os.path.basename(real_path)}/\n"
            f"The path you requested is a directory, not a file. I have listed its contents below for your convenience:\n\n"
            f"{listing_str}"
        )
    except Exception as e:
        return f"Error listing directory: {e}"





def _read_file_content(real_path: str, start: Optional[int], end: Optional[int]) -> str:
    """Dispatches reading logic based on file extension."""
    _ext = os.path.splitext(real_path)[1].lower()
    
    if _ext in ['.xlsx', '.xls']:
        return _read_excel(real_path)
    elif _ext in ['.docx', '.doc']:
        return _read_docx(real_path)
    elif _ext == '.pdf':
        return _read_pdf(real_path, start, end)
    elif _ext == '.html':
        return _read_html(real_path)
    else:
        # Code/Text Fallback. Using utils reading.
        content, _ = read_file_content(real_path)
        lang = detect_language(real_path)
        return _wrap_code_block(real_path, content, lang)


def _wrap_code_block(path: str, content: str, lang: str) -> str:
    """Reads a text file and returns it wrapped in a markdown code block."""
    filename = os.path.basename(path)
    # Special case: if lang is empty or txt, maybe use 'text' or nothing
    if not lang: lang = "text"
    
    # Return with markdown code block
    return f"# File: {filename}\n\n```{lang}\n{content}\n```"


# --- Inspection Helpers ---

def _inspect_excel(path: str) -> Dict[str, Any]:
    xl = pd.ExcelFile(path)
    sheets_info = {}
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet, nrows=5) # Peek top 5
        sheets_info[sheet] = {
            "columns": list(df.columns),
            "preview": df.head(2).to_dict(orient='records')
        }
    return {"sheets": list(xl.sheet_names), "details": sheets_info}


def _inspect_docx(path: str) -> Dict[str, Any]:
    doc = docx.Document(path)
    headings = []
    for para in doc.paragraphs:
        if para.style.name.startswith('Heading'):
            headings.append({"style": para.style.name, "text": para.text})
    
    return {
        "headings_count": len(headings),
        "headings": headings[:20] if len(headings) > 20 else headings
    }


def _inspect_pdf(path: str) -> Dict[str, Any]:
    reader = PdfReader(path)
    return {
        "pages": len(reader.pages),
        "metadata": reader.metadata
    }


def _read_pdf(path: str, start: Optional[int], end: Optional[int]) -> str:
    reader = PdfReader(path)
    total_pages = len(reader.pages)
    
    start_idx = (start - 1) if start else 0
    end_idx = end if end else total_pages
    start_idx = max(0, start_idx)
    end_idx = min(total_pages, end_idx)
    
    text = []
    text.append(f"# Document: {os.path.basename(path)}")
    text.append(f"*Metadata: {reader.metadata}*")
    text.append(f"*Pages: {start_idx+1} to {end_idx} (Total {total_pages})*")
    text.append("---")
    
    for i in range(start_idx, end_idx):
        page_text = reader.pages[i].extract_text()
        text.append(f"## Page {i+1}")
        text.append(page_text)
        text.append("---")
        
    return "\n\n".join(text)


def _read_docx(path: str) -> str:
    with open(path, "rb") as docx_file:
        result = mammoth.convert_to_markdown(docx_file)
        return f"# Document: {os.path.basename(path)}\n\n" + result.value


def _read_excel(path: str) -> str:
    xl = pd.ExcelFile(path)
    text = []
    text.append(f"# Spreadsheet: {os.path.basename(path)}")
    
    for sheet_name in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet_name)
        text.append(f"## Sheet: {sheet_name}")
        if not df.empty:
            text.append(df.to_markdown(index=False))
        else:
            text.append("*Empty Sheet*")
        text.append("\n")
        
    return "\n".join(text)


def _read_html(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    return f"# Document: {os.path.basename(path)}\n\n" + md(html_content)
