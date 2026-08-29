"""File subsystem constants.

Centralizes file-related limits, page sizes, and thresholds so they are not
scattered in tool implementations.
"""

# ====================== Size Units ======================
BYTES_PER_KB = 1024
BYTES_PER_MB = 1024 * 1024
BYTES_PER_GB = 1024 * 1024 * 1024

# ====================== File I/O Limits ======================
#: Files larger than this are considered "large" and may be handled specially.
LARGE_FILE_THRESHOLD = 10 * BYTES_PER_MB  # 10MB

#: Maximum number of file-system entries returned in a single listing/page.
DEFAULT_MAX_ENTRIES = 200

#: Default page size for paginated file results.
DEFAULT_PAGE_SIZE = 100

#: Maximum lines returned by read_file in one call.
MAX_LINES_PER_CALL = 1000

#: Maximum number of children shown for a single directory node in annotated tree.
FILE_TREE_FILE_LIMIT = 50

#: Maximum number of grep matches displayed to the user.
MAX_MATCHES = 100

#: Number of preview lines shown around a find_files match.
MAX_PREVIEW_LINES = 3

#: Maximum outline entries returned by outline tools.
OUTLINE_MAX_ENTRIES = 100

# ====================== Outline Detection ======================
#: Patterns used to detect section headings when generating file outlines.
OUTLINE_PATTERNS = {
    "python": [
        r"^\s*(class|def|async def)\s+\w+",
    ],
    "javascript": [
        r"^\s*(function|const|let|var|class)\s+\w+",
        r"^\s*\w+\s*[:=]\s*(function|\\(.*?\\)\s*=>)",
    ],
    "typescript": [
        r"^\s*(function|const|let|var|class|interface|type)\s+\w+",
        r"^\s*\w+\s*[:=]\s*(function|\\(.*?\\)\s*=>)",
    ],
    "java": [
        r"^\s*(public|private|protected)?\s*(class|interface|enum|void|static)?\s*\w+\s*\\(",
        r"^\s*(public|private|protected)?\s*\w+\s+\w+\s*\\(",
    ],
    "go": [
        r"^\s*(func|type|var|const)\s+\w+",
    ],
    "rust": [
        r"^\s*(fn|struct|enum|impl|trait|const|static|type)\s+\w+",
    ],
    "csharp": [
        r"^\s*(public|private|protected|internal)?\s*(class|struct|interface|enum|void|static|async)?\s*\w+",
    ],
    "generic": [
        r"^\s*#{1,6}\s+",
        r"^\s*[-=]{3,}\s*$",
    ],
}

# ====================== Editor Strategy Thresholds ======================
#: Minimum similarity for a single replacement candidate to be accepted outright.
SINGLE_CANDIDATE_SIMILARITY_THRESHOLD = 0.0
#: Minimum similarity threshold when multiple candidates are available.
MULTIPLE_CANDIDATES_SIMILARITY_THRESHOLD = 0.3
