"""
File Type Configuration Module - Defines file types and document type configurations.
Ported from evoloop-engineer.
"""

from enum import Enum

from app.core.config import settings


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
    ".py",
    ".js",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".cs",
    ".php",
    ".rb",
    ".go",
    ".rs",
    ".ts",
    ".html",
    ".css",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".xml",
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
    ".pyc", ".so", ".exe", ".bin",
    ".tar", ".gz", ".tgz", ".jar", ".war", ".ear",
    ".o", ".a", ".lib",
    ".db", ".class",
]

# System and low-level programming languages
LOW_LEVEL_EXTENSIONS = [
    ".c", ".cpp", ".h", ".cs", ".go", ".java", ".m", ".rs",
]

# Scripting and dynamic languages
SCRIPT_EXTENSIONS = [
    ".py", ".rb", ".js", ".mjs", ".php", ".pl", ".pm", ".lua", ".sh", ".swift",
]
# Common Testing Related Patterns
TEST_FILE_PATTERNS = {
    "python": ["test_", "_test.py"],
    "javascript": [".test.js", ".spec.js", ".test.ts", ".spec.ts"],
    "go": ["_test.go"],
    "java": ["Test.java"],
}

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

# YAML specific extensions
YAML_EXTENSIONS = [".yaml", ".yml"]

# Documentation and text files
DOC_TEXT_EXTENSIONS = [
    ".md", ".mdx", ".rst", ".txt", ".sql", ".xsq",
]

# Extensions allowed for logic-less document management (e.g. facades.write_document)
ALLOWED_DOC_EXTENSIONS = [
    ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html", ".htm", ".css",
    ".xml", ".rst", ".toml", ".ini", ".log",
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
SOURCE_MAP_EXTENSIONS = [".map", ".sourcemap"]

# ====================== File Filtering Configuration ======================

# Development environment blacklisted directories
DEV_ENV_DIRS = [
    ".venv", "venv", "env", ".idea", ".vscode", ".git", ".github", ".gitlab", ".vs",
]

# Cache and temporary file directories
CACHE_TEMP_DIRS = [
    "__pycache__", ".pytest_cache", ".tmp",
]

# Build and deploy related directories
BUILD_DEPLOY_DIRS = [
    "dist",
    "build",
    "node_modules",
    "vendor",
    "cdk.out",
    ".aws-sam",
    ".terraform",
    ".angular",
    ".next",
    "_nuxt",
    "bin",
    "obj",
    "packages",
    "coverage",
    ".output",
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
    r"\.git/",
    r"\.github/",
    r"node_modules/",
    r"vendor/",
    r"venv/",
    r"__pycache__/",
    r"\.pyc",
    r"\.DS_Store",
    r"\.env",
    r"\.lock",
    r"package-lock\.json",
    r"yarn\.lock",
    r"composer\.lock",
    r"poetry\.lock",
]

# All blacklisted file extensions
BLACKLIST_FILE_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS + AUDIO_EXTENSIONS + BINARY_EXTENSIONS

# All whitelist file extensions
WHITELIST_FILE_EXTENSIONS = (
    LOW_LEVEL_EXTENSIONS
    + SCRIPT_EXTENSIONS
    + FUNCTIONAL_EXTENSIONS
    + WEB_EXTENSIONS
    + CONFIG_EXTENSIONS
    + DOC_TEXT_EXTENSIONS
)

# Default excluded directories and files
DEFAULT_EXCLUDED_DIRS = BLACKLIST_DIRS
DEFAULT_EXCLUDED_FILES = BLACKLIST_FILES
DEFAULT_EXCLUDED_EXTENSIONS = BLACKLIST_FILE_EXTENSIONS
DEFAULT_INCLUDED_EXTENSIONS = WHITELIST_FILE_EXTENSIONS

# Directories likely to contain compressed code
LIKELY_COMPRESSED_CODE_DIRS = [
    "dist",
    "build",
    "vendor",
    "node_modules",
    "cdn",
    "assets/vendor",
    "public/assets",
    "static/vendor",
]

# Software project identification indicators
SOFTWARE_INDICATORS = {
    "package.json",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "requirements.txt",
    "Cargo.toml",
    "Gemfile",
    "composer.json",
    "Makefile",
    "tsconfig.json",
    "pyproject.toml",
    "setup.py",
    "pnpm-lock.yaml",
}

SOFTWARE_DIRECTORIES = {
    "src",
    "app",
    "lib",
    "pkg",
    "cmd",
}

# Identification patterns for main files: Entry point patterns
ENTRY_PATTERNS = [
    "main.py",
    "app.py",
    "index.js",
    "server.js",
    "main.go",
    "Main.java",
    "Program.cs",
    "index.php",
    "main.rs",
]

# Identification patterns for main files: Configuration patterns
CONFIG_PATTERNS = [
    "config",
    "settings",
    ".env",
    ".gitignore",
    "dockerfile",
    "docker-compose",
    "requirements.txt",
    "package.json",
    "setup.py",
    "pyproject.toml",
    "Cargo.toml",
]

IMPORTANT_PATTERNS = [
    "/api/",
    "controller",
    "service",
    "model",
    "main",
    "app",
    "core",
    "index",
    "base",
    "utils",
    "common",
    "component",
]

# Compressed/Obfuscated file identification
COMPRESSED_FILE_PATTERNS = [
    r"\.min\.(js|css|html)$",  # Minified JS/CSS
    r"\.bundle\.(js|css)$",  # Bundled files
    r"\.compiled\.(js|css)$",  # Compiled files
    r"\.umd\.js$",  # UMD modules
    r"\.(map|gzip|br)$",  # Source maps and compressed files
    r"-[a-f0-9]{8,}\.js$",  # JS files with hash
    r"\.[a-f0-9]{8,}\.chunk\.js$",  # Webpack chunks
    r"\.chunk\.[a-f0-9]{8,}\.(js|css)$",  # Chunk files
    r"vendors\-[a-f0-9]{6,}\.(js|css)$",  # Vendor files
]

# Extensions that are commonly compressed or minified
COMPRESSIBLE_EXTENSIONS = {".js", ".css", ".html", ".map", ".json"}

# Code quality thresholds (for compressed code detection)
CODE_QUALITY_THRESHOLDS = {
    "max_line_length": 500,  # Maximum line length
    "min_newline_ratio": 0.005,  # Minimum newline ratio
    "max_char_entropy": 7.0,  # Maximum character entropy (measure of randomness)
    "min_whitespace_ratio": 0.1,  # Minimum whitespace ratio
    "max_semicolon_ratio": 0.05,  # Maximum semicolon ratio
    "max_file_size_mb": 1.0,  # Maximum file size (MB)
    "sample_size": 4096,  # Content sampling size (bytes)
}

# File encoding attempt order
FILE_ENCODINGS = ["utf-8", "latin-1", "utf-16", "ascii"]

# Merged from document_reader.py
EXTENSION_MAP = {
    # Python
    ".py": "python",
    ".pyi": "python",
    # JavaScript/TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    # Web
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    # Java/JVM
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    # C/C++
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    # Go
    ".go": "go",
    # Rust
    ".rs": "rust",
    # Scripting
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".pl": "perl",
    ".rb": "ruby",
    ".php": "php",
    ".lua": "lua",
    # Data/Config
    ".json": "json",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".sql": "sql",
    ".md": "markdown",
    # Other
    ".cs": "csharp",
    ".swift": "swift",
    ".r": "r",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
}

# Mapping shebang patterns to language
SHEBANG_MAP = {
    "python": ["python"],
    "bash": ["bash", "sh"],
    "javascript": ["node"],
}

# ====================== Semantic / Structural Analysis Constants ======================
# Languages supported for semantic extraction (API, DB, etc.)
SEMANTIC_LANGUAGE_MAP = {
    # Core languages
    "python": [".py", ".pyi"],
    "typescript": [".ts", ".tsx", ".mts", ".cts"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "java": [".java"],
    "go": [".go"],
    "csharp": [".cs"],
    # Extended languages
    "php": [".php"],
    "ruby": [".rb"],
    "rust": [".rs"],
    "kotlin": [".kt", ".kts"],
    "swift": [".swift"],
    "sql": [".sql"],
    "vue": [".vue"],
}
SEMANTIC_EXTENSIONS = {ext for exts in SEMANTIC_LANGUAGE_MAP.values() for ext in exts}

# Extensions allowed for full repository indexing (Searchable Codebase)
# Includes all semantic languages + documentation + common text-based configs
INDEXABLE_EXTENSIONS = SEMANTIC_EXTENSIONS | {
    ".md", ".markdown", ".txt", ".sh", ".bash", ".c", ".h", ".cpp", ".hpp",
    ".yaml", ".yml", ".toml", ".json", ".sql", ".pdf", ".docx", ".xlsx", ".csv",
    ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".mp3", ".wav", ".mp4", ".mov", ".avi"
}

# ====================== Model Constants ======================
MODEL_GPT4O = "gpt-4o"
MODEL_CLAUDE_SONNET = "claude-3-5-sonnet-20240620"

# ====================== Security / Filter Patterns ======================
SUSPICIOUS_JS_PATTERNS = [
    r"\(function\([a-z],[a-z],[a-z]\)",
    r'new Function\(["\'](.*?)["\']',
    r"eval\(.*?\)",
    r"\\x[0-9a-f]{2}",
    r"\\u[0-9a-f]{4}",
]


# ====================== RAG / Search Constants ======================
# Search related
DEFAULT_SEARCH_TOP_K = settings.DEFAULT_SEARCH_TOP_K
MAX_SEARCH_DEPTH = settings.MAX_SEARCH_DEPTH
MIN_RELEVANCE_SCORE = settings.MIN_RELEVANCE_SCORE

# Chunking related
DEFAULT_CHUNK_SIZE = settings.DEFAULT_CHUNK_SIZE
MAX_CHUNK_SIZE = settings.MAX_CHUNK_SIZE
DEFAULT_CHUNK_OVERLAP = settings.DEFAULT_CHUNK_OVERLAP

# Memory related
MAX_SESSION_HISTORY = settings.MAX_SESSION_HISTORY
MEMORY_RELEVANCE_THRESHOLD = settings.MEMORY_RELEVANCE_THRESHOLD
MAX_MEMORY_ITEMS = settings.MAX_MEMORY_ITEMS


# ====================== Workflow / Task Constants ======================
class RoutingTarget(str, Enum):
    """Supported routing targets for the agent system."""
    OPERATOR = "operator"
    DEEP_RESEARCHER = "deep_researcher"
    DOCUMENTER = "documenter"
    CHAT = "chat"
    FINISH = "finish"
    DYNAMIC_SPECIALIST = "dynamic_specialist"
    FLASH_BRAIN = "flash_brain"


TASK_TYPES = [
    "code_generation",
    "bug_fix",
    "code_explanation",
    "refactoring",
    "architecture_analysis",
]

ROUTING_TARGETS = {
    RoutingTarget.OPERATOR: "Primary worker for coding, testing, and architecture.",
    RoutingTarget.DEEP_RESEARCHER: "Web search and information gathering.",
    RoutingTarget.DOCUMENTER: "Documentation and wiki generation.",
    RoutingTarget.CHAT: "Ambiguous requests requiring clarification.",
    RoutingTarget.FINISH: "Task completion.",
    RoutingTarget.DYNAMIC_SPECIALIST: "Temporary, specialized sub-agent (e.g., SQLRunner).",
    RoutingTarget.FLASH_BRAIN: "Fast, low-cost reasoning or memory lookup.",
}

WORKFLOW_STATUS = ["pending", "running", "completed", "failed", "cancelled"]


# ====================== AI Model Capabilities ======================
# Context Window Sizes (Tokens)
CONTEXT_SIZES = {
    "openai": {
        "gpt-3.5-turbo": 16384,
        "gpt-4": 8192,
        "gpt-4-turbo": 128000,
        "gpt-4o": 128000,
        "default": 16384,
    },
    "anthropic": {
        "claude-instant-1": 100000,
        "claude-2": 100000,
        "claude-3-opus": 200000,
        "claude-3-sonnet": 200000,
        "claude-3-haiku": 200000,
        "claude-3-5-sonnet": 200000,
        "default": 100000,
    },
    "dashscope": {
        "qwen-turbo": 32000,
        "qwen-plus": 32000,
        "qwen-max": 1000000,
        "default": 32000,
    },
    "deepseek": {
        "deepseek-chat": 64000,
        "deepseek-coder": 64000,
        "default": 64000,
    },
    "local": {
        "llama3": 8192,
        "mistral": 8192,
        "default": 4096,
    }
}

# Max Tokens per Chunk (for Embedding)
MAX_TOKENS_PER_CHUNK = {
    "openai": {
        "text-embedding-ada-002": 8192,
        "text-embedding-3-small": 8192,
        "text-embedding-3-large": 8192,
        "default": 8192,
    },
    "dashscope": {
        "text-embedding-v1": 2048,
        "text-embedding-v2": 2048,
        "text-embedding-v3": 8192,
        "default": 2048,
    },
    "cohere": {
        "embed-english-v2.0": 2048,
        "embed-multilingual-v2.0": 2048,
        "default": 2048,
    },
    "huggingface": {
        "sentence-transformers/all-mpnet-base-v2": 512,
        "sentence-transformers/all-MiniLM-L6-v2": 512,
        "sentence-transformers/paraphrase-multilingual-mpnet-base-v2": 512,
        "BAAI/bge-large-en-v1.5": 512,
        "BAAI/bge-base-en-v1.5": 512,
        "BAAI/bge-small-en-v1.5": 512,
        "BAAI/bge-large-zh-v1.5": 512,
        "BAAI/bge-base-zh-v1.5": 512,
        "default": 512,
    },
    "local": {
        "all-MiniLM-L6-v2": 512,
        "all-mpnet-base-v2": 512,
        "e5-large-v2": 1024,
        "bge-large": 1024,
        "bge-small": 512,
        "nomic-embed-text": 1024,
        "gte-large": 1024,
        "gte-small": 512,
        "default": 512,
    },
    "default": 2048,
}

# ====================== Language Constants ======================
LANGUAGE_MAP = {
    "en": "English",
    "zh": "Mandarin Chinese (中文)",
}

# ====================== Output Constraints ======================
MAX_OUTPUT_LENGTH = 20000  # Max characters for tool output before truncation
