"""
File Type Configuration Module - Defines file types and document type configurations.
Ported from evoloop-engineer.
"""

# ====================== Engine Constants ======================
DEFAULT_PROJECT_ID = 0

# Default max context tokens fallback (128K) for unknown/unconfigured models
DEFAULT_MAX_CONTEXT_TOKENS = 128_000

# Default internal LLM generation budget (e.g. summarization/extraction)
DEFAULT_INTERNAL_LLM_TOKENS = 4_000

# ====================== Cross-subsystem Event Constants ======================
#: Rewind requested event type (used by engine, memory, file, learning, planning)
REWIND_REQUESTED = "rewind.requested"
#: Messages cleanup event type (used by engine and evocloud sync)
MESSAGES_CLEANUP = "rewind.messages.cleanup"

# ====================== Cross-subsystem Cache Keys ======================
#: Prefix for platform-specific dynamic app bundle ID sets (atlas + environment)
CACHE_KEY_DYNAMIC_APPS_PREFIX = "system:dynamic_apps"


# ====================== File Type Configuration ======================

# Image file extensions
IMAGE_EXTENSIONS = [
    ".bmp",
    ".gif",
    ".ico",
    ".jpg",
    ".jpeg",
    ".png",
    ".svg",
    ".tiff",
    ".webp",
]

# Video file extensions
VIDEO_EXTENSIONS = [
    ".avi",
    ".flv",
    ".mov",
    ".mpeg",
    ".mp4",
    ".wmv",
]

# Audio file extensions
AUDIO_EXTENSIONS = [
    ".mp3",
]

# Compressed and binary file extensions
BINARY_EXTENSIONS = [
    ".zip",
    ".rar",
    ".7z",
    ".zlib",
    ".dll",
    ".ipynb",  # Jupyter notebooks
    ".pyc",
    ".so",
    ".exe",
    ".bin",
    ".tar",
    ".gz",
    ".tgz",
    ".jar",
    ".war",
    ".ear",
    ".o",
    ".a",
    ".lib",
    ".db",
    ".class",
]

# Source map files
SOURCE_MAP_EXTENSIONS = [".map", ".sourcemap"]

# ====================== File Filtering Configuration ======================

# Development environment blacklisted directories
DEV_ENV_DIRS = [
    ".venv",
    "venv",
    "env",
    ".idea",
    ".vscode",
    ".git",
    ".github",
    ".gitlab",
    ".vs",
]

# Cache and temporary file directories
CACHE_TEMP_DIRS = [
    "__pycache__",
    ".pytest_cache",
    ".tmp",
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
    ".DS_Store",
]

# All blacklisted files
BLACKLIST_FILES = DEPENDENCY_FILES + SPECIAL_PYTHON_FILES

# All blacklisted file extensions
BLACKLIST_FILE_EXTENSIONS = (
    IMAGE_EXTENSIONS + VIDEO_EXTENSIONS + AUDIO_EXTENSIONS + BINARY_EXTENSIONS
)

# Default excluded directories and files
DEFAULT_EXCLUDED_DIRS = BLACKLIST_DIRS
DEFAULT_EXCLUDED_FILES = BLACKLIST_FILES
DEFAULT_EXCLUDED_EXTENSIONS = BLACKLIST_FILE_EXTENSIONS

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
    ".md",
    ".markdown",
    ".txt",
    ".sh",
    ".bash",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".sql",
    ".pdf",
    ".docx",
    ".xlsx",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
    ".mp3",
    ".wav",
    ".mp4",
    ".mov",
    ".avi",
}

# ====================== Security / Filter Patterns ======================
SUSPICIOUS_JS_PATTERNS = [
    r"\(function\([a-z],[a-z],[a-z]\)",
    r'new Function\(["\'](.*?)["\']',
    r"eval\(.*?\)",
    r"\\x[0-9a-f]{2}",
    r"\\u[0-9a-f]{4}",
]

# ====================== Language Constants ======================
LANGUAGE_MAP = {
    "en": "English",
    "zh": "Mandarin Chinese (中文)",
}


