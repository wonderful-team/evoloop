
import os
import logging
import json
import sqlite3
import urllib.request
import tempfile
import shutil
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List, Union

# Lazy imports
try:
    import pandas as pd
    import docx
    import mammoth
    from pypdf import PdfReader
    from markdownify import markdownify as md
except ImportError:
    pass

logger = logging.getLogger(__name__)

def _ensure_local_path(file_path: str) -> str:
    """
    If file_path is a URL, download it to a temporary file and return the temp path.
    Otherwise return the original path.
    """
    if file_path.startswith(('http://', 'https://')):
        try:
            # Try to guess extension from url or header
            parsed = urlparse(file_path)
            ext = os.path.splitext(parsed.path)[1]
            if not ext:
                # Fallback content-type mapping if needed, or just default
                pass
                
            fd, temp_path = tempfile.mkstemp(suffix=ext)
            os.close(fd)
            
            with urllib.request.urlopen(file_path) as response, open(temp_path, 'wb') as out_file:
                 shutil.copyfileobj(response, out_file)
            
            logger.info(f"Downloaded {file_path} to {temp_path}")
            return temp_path
        except Exception as e:
            logger.error(f"Failed to download remote file {file_path}: {e}")
            raise ValueError(f"Failed to download remote file: {e}")
            
    return file_path

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
        real_path = _ensure_local_path(file_path)
    except Exception as e:
        return json.dumps({"error": str(e)})

    if not os.path.exists(real_path):
        return json.dumps({"error": f"File not found: {real_path}"})

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
            
        return json.dumps(metadata, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Inspection failed: {e}")
        return json.dumps({"error": str(e)})

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
        real_path = _ensure_local_path(file_path)
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
        df.columns = [c.strip().replace(' ', '_') for c in df.columns]
        
        # Create in-memory SQLite DB
        conn = sqlite3.connect(':memory:')
        df.to_sql('data', conn, index=False, if_exists='replace')
        
        # Execute Query
        result_df = pd.read_sql_query(sql_query, conn)
        conn.close()
        
        return result_df.to_json(orient='records', force_ascii=False)
        
    except Exception as e:
        return f"SQL Execution Error: {str(e)}"

def read_document(file_path: str, start_page: Optional[int] = None, end_page: Optional[int] = None) -> str:
    """
    Read and parse content from various document formats (PDF, DOCX, XLSX, MD, TXT, HTML).
    Returns the content converted to Markdown format.

    Args:
        file_path (str): Absolute path to the file or URL.
        start_page (int, optional): Start page for PDF (1-based).
        end_page (int, optional): End page for PDF (1-based).
    """
    try:
        real_path = _ensure_local_path(file_path)
    except Exception as e:
        return f"Error: {str(e)}"

    if not os.path.exists(real_path):
        return f"Error: File not found: {real_path}"

    _ext = os.path.splitext(real_path)[1].lower()
    
    try:
        content = ""
        if _ext in ['.xlsx', '.xls']:
            content = _read_excel(real_path)
        elif _ext in ['.docx', '.doc']:
            content = _read_docx(real_path)
        elif _ext == '.pdf':
            content = _read_pdf(real_path, start_page, end_page)
        elif _ext == '.html':
            with open(real_path, 'r', encoding='utf-8') as f:
                content = md(f.read())
        else:
            # Fallback to text
            with open(real_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
                
        return content
    except Exception as e:
        logger.error(f"Read failed: {e}")
        return f"Error reading file: {str(e)}"

# --- Internal Helpers ---

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
    # Mammoth helps with HTML, but python-docx is better for structural inspection?
    # Let's use python-docx simply if available
    doc = docx.Document(path)
    # Extract headings (TOC approximation)
    headings = []
    for para in doc.paragraphs:
        if para.style.name.startswith('Heading'):
            headings.append({"style": para.style.name, "text": para.text})
    
    return {
        "headings_count": len(headings),
        "headings": headings[:20] if len(headings) > 20 else headings # Limit output
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

def _read_text(path: str) -> str:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f"# Document: {os.path.basename(path)}\n\n" + f.read()
