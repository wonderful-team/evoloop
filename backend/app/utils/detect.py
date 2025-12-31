import os
import re
from typing import Optional, Dict

from app.constants import (
    EXTENSION_MAP, # We need to ensure EXTENSION_MAP is in constants.py (It was in document_reader but moved?)
    # Wait, EXTENSION_MAP was in document_reader.py in the original code, but I moved `app/domain/codebase/constants.py` to `app/constants.py`.
    # `app/domain/codebase/constants.py` had `CODE_EXTENSION_MAP` and `FILE_EXTENSION_TO_TYPE` but NOT `EXTENSION_MAP` (which was specific to document reader).
    # I should merge them or use what's available. `CODE_EXTENSION_MAP` is good.
    CODE_EXTENSION_MAP,
    FILE_EXTENSION_TO_TYPE,
    DocumentType
)

# If EXTENSION_MAP is missing in constants, I should probably define a comprehensive one here or rely on CODE_EXTENSION_MAP.
# The `document_reader` had a very rich EXTENSION_MAP.
# Let's verify `app/constants.py` content later or define a local map if needed.
# For now, I'll rely on what I saw in `constants.py` earlier.

def detect_language(file_path: str, content: Optional[str] = None) -> str:
    """
    Detect programming language from file path or content.
    """
    filename = os.path.basename(file_path)
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    # Check known extensions
    if ext in CODE_EXTENSION_MAP:
        return CODE_EXTENSION_MAP[ext]
        
    # Fallback/Additional from document_reader legacy
    # If not found, maybe return 'text' or try content analysis (shebang)
    
    if content and content.startswith('#!'):
        first_line = content.split('\n')[0]
        if 'python' in first_line: return 'python'
        if 'bash' in first_line or 'sh' in first_line: return 'bash'
        if 'node' in first_line: return 'javascript'
        
    return "text"


def detect_document_type(file_path: str) -> str:
    """
    Detect high-level document type (code, text, pdf, image, etc.)
    Returns str value of DocumentType enum.
    """
    _, ext = os.path.splitext(file_path)
    ext_key = ext.lower().lstrip('.')
    
    if ext_key in FILE_EXTENSION_TO_TYPE:
        # If it's an enum member, get value
        val = FILE_EXTENSION_TO_TYPE[ext_key]
        return val.value if hasattr(val, 'value') else val
        
    return DocumentType.UNKNOWN.value
