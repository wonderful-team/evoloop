"""
File Type Configuration Module - Defines file types and document type configurations.
Ported from evoloop-engineer.
"""

from enum import Enum


# ====================== Document Type Enum ======================
class DocumentType(Enum):
    """Document type enumeration"""
    UNKNOWN = "unknown"
    TEXT = "text"
    PDF = "pdf"
    DOCX = "docx"
    CODE = "code"
    MARKDOWN = "markdown"
    EXCEL = "excel"
    CSV = "csv"
    HTML = "html"
    JUPYTER = "jupyter"
    JSON = "json"
    XML = "xml"


# ====================== File Type Configuration ======================

# Text file identification
TEXT_EXTENSIONS = [
    '.py', '.js', '.java', '.c', '.cpp', '.h', '.cs', '.php',
    '.rb', '.go', '.rs', '.ts', '.html', '.css', '.md',
    '.json', '.yml', '.yaml', '.xml'
]

# Image file extensions
IMAGE_EXTENSIONS = [
    ".bmp", ".gif", ".ico", ".jpg", ".jpeg", ".png", ".svg", ".tiff", ".webp",
]

# Video file extensions
VIDEO_EXTENSIONS = [
    ".avi", ".flv", ".mov", ".mpeg", ".mp4", ".wmv",
]

# Audio file extensions
AUDIO_EXTENSIONS = [
    ".mp3",
]

# Compressed and binary file extensions
BINARY_EXTENSIONS = [
    ".zip", ".rar", ".7z", ".zlib", ".dll", ".ipynb",  # Jupyter notebooks
]

# System and low-level programming languages
LOW_LEVEL_EXTENSIONS = [
    ".c", ".cpp", ".h", ".cs", ".go", ".java", ".m", ".rs",
]

# Scripting and dynamic languages
SCRIPT_EXTENSIONS = [
    ".py", ".rb", ".js", ".mjs", ".php", ".pl", ".pm", ".lua", ".sh", ".swift",
]

# Functional programming languages
FUNCTIONAL_EXTENSIONS = [
    ".el", ".ex", ".exs", ".elm", ".hs", ".ml", ".mli", ".scala",
]

# Web development related
WEB_EXTENSIONS = [
    ".html", ".htm", ".css", ".less", ".scss", ".jsx", ".ts", ".tsx", ".vue",
]

# Configuration files
CONFIG_EXTENSIONS = [
    ".cfg", ".conf", ".ini", ".json", ".properties", ".toml", ".xml", ".yaml", ".yml",
]

# Documentation and text files
DOC_TEXT_EXTENSIONS = [
    ".md", ".mdx", ".rst", ".txt", ".sql", ".xsq",
]

# Mapping file extension to document type
FILE_EXTENSION_TO_TYPE = {
    # Text files
    "txt": DocumentType.TEXT,

    # Document files
    "pdf": DocumentType.PDF,
    "docx": DocumentType.DOCX,
    "doc": DocumentType.DOCX,

    # Code files
    "py": DocumentType.CODE,
    "js": DocumentType.CODE,
    "java": DocumentType.CODE,
    "c": DocumentType.CODE,
    "cpp": DocumentType.CODE,
    "cs": DocumentType.CODE,
    "go": DocumentType.CODE,
    "rs": DocumentType.CODE,
    "php": DocumentType.CODE,
    "rb": DocumentType.CODE,
    "swift": DocumentType.CODE,
    "kt": DocumentType.CODE,
    "ts": DocumentType.CODE,
    "sh": DocumentType.CODE,

    # Markup languages
    "md": DocumentType.MARKDOWN,
    "markdown": DocumentType.MARKDOWN,
    "html": DocumentType.HTML,
    "htm": DocumentType.HTML,
    "xml": DocumentType.XML,
    "json": DocumentType.JSON,

    # Spreadsheets
    "xlsx": DocumentType.EXCEL,
    "xls": DocumentType.EXCEL,
    "csv": DocumentType.CSV,

    # Jupyter notebooks
    "ipynb": DocumentType.JUPYTER,
}

# Source map files
SOURCE_MAP_EXTENSIONS = [
    ".map",
    ".sourcemap"
]

# ====================== File Filtering Configuration ======================

# Development environment blacklisted directories
DEV_ENV_DIRS = [
    ".venv", "venv", "env", ".idea", ".vscode", ".git", ".github", ".gitlab",
]

# Cache and temporary file directories
CACHE_TEMP_DIRS = [
    "__pycache__", ".pytest_cache", ".tmp",
]

# Build and deploy related directories
BUILD_DEPLOY_DIRS = [
    "dist", "build", "node_modules", "cdk.out", ".aws-sam",
    ".terraform", ".angular", ".next", "_nuxt",
]

# All blacklisted directories
BLACKLIST_DIRS = DEV_ENV_DIRS + CACHE_TEMP_DIRS + BUILD_DEPLOY_DIRS

# Dependency management blacklisted files
DEPENDENCY_FILES = [
    "package-lock.json",
    "package.json",
]

# Special Python files
SPECIAL_PYTHON_FILES = [
    "__init__.py",
]

# All blacklisted files
BLACKLIST_FILES = DEPENDENCY_FILES + SPECIAL_PYTHON_FILES

# Excluded directory and file patterns
EXCLUDED_PATTERNS = [
    r'\.git/',
    r'\.github/',
    r'node_modules/',
    r'venv/',
    r'__pycache__/',
    r'\.pyc',
    r'\.DS_Store',
    r'\.env',
    r'\.lock',
    r'package-lock\.json',
    r'yarn\.lock',
    r'composer\.lock',
    r'poetry\.lock',
]

# All blacklisted file extensions
BLACKLIST_FILE_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS + AUDIO_EXTENSIONS + BINARY_EXTENSIONS

# All whitelist file extensions
WHITELIST_FILE_EXTENSIONS = (
    LOW_LEVEL_EXTENSIONS +
    SCRIPT_EXTENSIONS +
    FUNCTIONAL_EXTENSIONS +
    WEB_EXTENSIONS +
    CONFIG_EXTENSIONS +
    DOC_TEXT_EXTENSIONS
)

# Default excluded directories and files
DEFAULT_EXCLUDED_DIRS = BLACKLIST_DIRS
DEFAULT_EXCLUDED_FILES = BLACKLIST_FILES
DEFAULT_EXCLUDED_EXTENSIONS = BLACKLIST_FILE_EXTENSIONS
DEFAULT_INCLUDED_EXTENSIONS = WHITELIST_FILE_EXTENSIONS

# Directories likely to contain compressed code
LIKELY_COMPRESSED_CODE_DIRS = [
    "dist", "build", "vendor", "node_modules", "cdn",
    "assets/vendor", "public/assets", "static/vendor",
]

# Identification patterns for main files: Entry point patterns
ENTRY_PATTERNS = [
    "main.py", "app.py", "index.js", "server.js", "main.go",
    "Main.java", "Program.cs", "index.php", "main.rs"
]

# Identification patterns for main files: Configuration patterns
CONFIG_PATTERNS = [
    "config", "settings", ".env", ".gitignore", "dockerfile",
    "docker-compose", "requirements.txt", "package.json",
    "setup.py", "pyproject.toml", "Cargo.toml"
]

IMPORTANT_PATTERNS = [
    "/api/", "controller", "service", "model", "main", "app", "core",
    "index", "base", "utils", "common", "component"
]

# Compressed/Obfuscated file identification
COMPRESSED_FILE_PATTERNS = [
    r"\.min\.(js|css|html)$",  # Minified JS/CSS
    r"\.bundle\.(js|css)$",  # Bundled files
    r"\.compiled\.(js|css)$",  # Compiled files
    r'\.umd\.js$',  # UMD modules
    r'\.(map|gzip|br)$',  # Source maps and compressed files
    r"-[a-f0-9]{8,}\.js$",   # JS files with hash
    r"\.[a-f0-9]{8,}\.chunk\.js$",  # Webpack chunks
    r'\.chunk\.[a-f0-9]{8,}\.(js|css)$',  # Chunk files
    r'vendors\-[a-f0-9]{6,}\.(js|css)$',  # Vendor files
]

# Code quality thresholds (for compressed code detection)
CODE_QUALITY_THRESHOLDS = {
    "max_line_length": 500,        # Maximum line length
    "min_newline_ratio": 0.005,    # Minimum newline ratio
    "max_char_entropy": 7.0,       # Maximum character entropy (measure of randomness)
    "min_whitespace_ratio": 0.1,   # Minimum whitespace ratio
    "max_semicolon_ratio": 0.05,   # Maximum semicolon ratio
    "max_file_size_mb": 1.0,       # Maximum file size (MB)
    "sample_size": 4096,           # Content sampling size (bytes)
}

# File encoding attempt order
FILE_ENCODINGS = ['utf-8', 'latin-1', 'utf-16', 'ascii']

# Code File Extension Map
CODE_EXTENSION_MAP = {
    # Python
    ".py": "python",
    ".pyi": "python",

    # JavaScript/TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",

    # Java
    ".java": "java",

    # C/C++
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",

    # Go
    ".go": "go",

    # Ruby
    ".rb": "ruby",

    # PHP
    ".php": "php",

    # C#
    ".cs": "c_sharp",

    # Rust
    ".rs": "rust",

    # Swift
    ".swift": "swift",

    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".sh": "shell"
}

# Merged from document_reader.py
EXTENSION_MAP = {
    # Python
    ".py": "python", ".pyi": "python",
    # JavaScript/TypeScript
    ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    # Web
    ".html": "html", ".css": "css", ".scss": "scss", ".less": "less",
    # Java/JVM
    ".java": "java", ".kt": "kotlin", ".scala": "scala",
    # C/C++
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    # Go
    ".go": "go",
    # Rust
    ".rs": "rust",
    # Scripting
    ".sh": "bash", ".bash": "bash", ".zsh": "bash", ".pl": "perl", ".rb": "ruby", ".php": "php", ".lua": "lua",
    # Data/Config
    ".json": "json", ".xml": "xml", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".ini": "ini",
    ".sql": "sql", ".md": "markdown",
    # Other
    ".cs": "csharp", ".swift": "swift", ".r": "r", ".dart": "dart", ".vue": "vue", ".svelte": "svelte"
}

# ====================== Model Constants ======================
MODEL_GPT4O = "gpt-4o"
MODEL_CLAUDE_SONNET = "claude-3-5-sonnet-20240620"

# ====================== Security / Filter Patterns ======================
SUSPICIOUS_JS_PATTERNS = [
    r'\(function\([a-z],[a-z],[a-z]\)',
    r'new Function\(["\'](.*?)["\']',
    r'eval\(.*?\)',
    r'\\x[0-9a-f]{2}',
    r'\\u[0-9a-f]{4}'
]

