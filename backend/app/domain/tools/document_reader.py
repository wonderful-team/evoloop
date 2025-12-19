
import os
import logging
from typing import Dict, Any, Optional

# Lazy imports to avoid heavy dependencies if not used
try:
    import pandas as pd
    import docx
    import mammoth
    from pypdf import PdfReader
    from markdownify import markdownify as md
except ImportError:
    pass

logger = logging.getLogger(__name__)

def read_document(file_path: str, start_page: Optional[int] = None, end_page: Optional[int] = None) -> str:
    """
    Read and parse content from various document formats (PDF, DOCX, XLSX, MD, TXT, HTML).
    Returns the content converted to Markdown format.

    Args:
        file_path (str): Absolute path to the file.
        start_page (int, optional): Start page for PDF (1-based).
        end_page (int, optional): End page for PDF (1-based).

    """
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"
    
    _ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if _ext == '.pdf':
            return _read_pdf(file_path, start_page, end_page)
        elif _ext in ['.docx', '.doc']:
            return _read_docx(file_path)
        elif _ext in ['.xlsx', '.xls']:
            return _read_excel(file_path)
        elif _ext in ['.html', '.htm']:
            return _read_html(file_path)
        elif _ext in ['.md', '.txt', '.py', '.json', '.xml', '.yaml', '.yml']:
            return _read_text(file_path)
        else:
            return f"Error: Unsupported file extension {_ext}"
    except Exception as e:
        logger.error(f"Failed to read document {file_path}: {e}")
        return f"Error reading file: {str(e)}"

def _read_pdf(path: str, start: Optional[int], end: Optional[int]) -> str:
    reader = PdfReader(path)
    total_pages = len(reader.pages)
    
    start_idx = (start - 1) if start else 0
    end_idx = end if end else total_pages
    
    # Clamp
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
    # Use mammoth for better HTML/Markdown conversion if structure matters
    with open(path, "rb") as docx_file:
        result = mammoth.convert_to_markdown(docx_file)
        return f"# Document: {os.path.basename(path)}\n\n" + result.value

def _read_excel(path: str) -> str:
    # Read all sheets
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
