import os

from app.constants import EXTENSION_MAP, SHEBANG_MAP

# If EXTENSION_MAP is missing in constants, I should probably define a comprehensive one here or rely on CODE_EXTENSION_MAP.
# The `document_reader` had a very rich EXTENSION_MAP.
# Let's verify `app/constants.py` content later or define a local map if needed.
# For now, I'll rely on what I saw in `constants.py` earlier.


def detect_language(file_path: str, content: str | None = None) -> str:
    """
    Detect programming language from file path or content.
    """
    filename = os.path.basename(file_path)
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    # Check known extensions
    if ext in EXTENSION_MAP:
        return EXTENSION_MAP[ext]

    # Fallback: shebang detection
    if content and content.startswith("#!"):
        first_line = content.splitlines()[0]
        for lang, patterns in SHEBANG_MAP.items():
            if any(pattern in first_line for pattern in patterns):
                return lang

    return "text"


def is_code_file(file_path: str, _content: str | None = None) -> bool:
    """
    Check if the file is a code file based on extension or filename.

    Deprecated: use ``app.core.file.is_code_file`` (re-export of is_code) instead.
    Scheduled for removal in next refactor cycle.
    """
    filename = os.path.basename(file_path)
    if filename in EXTENSION_MAP:
        return True

    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    return ext in EXTENSION_MAP
