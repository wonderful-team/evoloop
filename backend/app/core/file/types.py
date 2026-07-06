"""
File Type and Category Detection.
Consolidated from legacy app.utils.file_type.
"""
import mimetypes
import os
import re
from pathlib import Path
from typing import List, Set

# --- Constants: Extension Sets ---

# Binary file extensions
BINARY_EXTENSIONS: Set[str] = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg',
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm',
    '.exe', '.dll', '.so', '.dylib', '.bin',
    '.db', '.sqlite', '.sqlite3',
    '.woff', '.woff2', '.ttf', '.otf', '.eot',
    '.ico', '.icns',
}

# Image file extensions
IMAGE_EXTENSIONS: Set[str] = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp',
    '.svg', '.ico', '.icns', '.raw', '.cr2', '.nef', '.heic',
}

# Video file extensions
VIDEO_EXTENSIONS: Set[str] = {
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.f4v', '.webm',
    '.mkv', '.m4v', '.3gp', '.mpg', '.mpeg', '.mpe', '.mpv',
}

# Audio file extensions
AUDIO_EXTENSIONS: Set[str] = {
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a',
    '.opus', '.aiff', '.au', '.ra', '.ram',
}

# Archive file extensions
ARCHIVE_EXTENSIONS: Set[str] = {
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz', '.zipx',
}

# Document file extensions
DOCUMENT_EXTENSIONS: Set[str] = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.odp', '.rtf', '.txt', '.md', '.csv',
}

# Code file extensions (common)
CODE_EXTENSIONS: Set[str] = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.cc', '.cxx',
    '.h', '.hpp', '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt',
    '.scala', '.r', '.m', '.mm', '.pl', '.pm', '.lua', '.groovy',
    '.sql', '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
    '.html', '.htm', '.css', '.scss', '.sass', '.less', '.xml', '.json',
    '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.properties',
}

# Test file patterns
TEST_FILE_PATTERNS: List[str] = [
    r'^test_.*\.py$',
    r'.*_test\.py$',
    r'^spec_.*\.(js|ts)$',
    r'.*\.spec\.(js|ts)$',
    r'.*\.test\.(js|ts|tsx|jsx)$',
    r'^.*Test\.java$',
    r'^.*_test\.go$',
    r'^.*_spec\.rb$',
    r'^test_.*\.rs$',
    r'.*\.test\.php$',
]

# --- Helper Functions ---

def get_extension(path: str) -> str:
    """Get lowercase file extension including the dot."""
    return Path(path).suffix.lower()

def is_binary(path: str) -> bool:
    """
    Check if a file is likely binary based on extension and content sampling.
    """
    ext = get_extension(path)
    if ext in BINARY_EXTENSIONS:
        return True
    
    # Content-based detection for unknown extensions
    if os.path.exists(path) and os.path.isfile(path):
        try:
            with open(path, 'rb') as f:
                chunk = f.read(8192)
                # Check for null bytes
                if b'\x00' in chunk:
                    return True
                # Check for high ratio of non-printable characters
                if len(chunk) > 0:
                    non_printable = sum(1 for b in chunk if b < 32 and b not in (9, 10, 13))
                    if non_printable / len(chunk) > 0.3:
                        return True
        except (IOError, OSError):
            pass
    return False

def is_text(path: str) -> bool:
    """Check if a file is likely a text file."""
    return not is_binary(path)

def is_image(path: str) -> bool:
    """Check if file is an image."""
    return get_extension(path) in IMAGE_EXTENSIONS

def is_video(path: str) -> bool:
    """Check if file is a video."""
    return get_extension(path) in VIDEO_EXTENSIONS

def is_audio(path: str) -> bool:
    """Check if file is an audio file."""
    return get_extension(path) in AUDIO_EXTENSIONS

def is_archive(path: str) -> bool:
    """Check if file is an archive."""
    return get_extension(path) in ARCHIVE_EXTENSIONS

def is_document(path: str) -> bool:
    """Check if file is a document."""
    return get_extension(path) in DOCUMENT_EXTENSIONS

def is_code(path: str) -> bool:
    """Check if file is a code file."""
    ext = get_extension(path)
    if ext in CODE_EXTENSIONS:
        return True
    
    # Check shebang for extensionless scripts
    if os.path.exists(path) and os.path.isfile(path) and ext == '':
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
                if first_line.startswith('#!'):
                    return True
        except (IOError, OSError):
            pass
    return False

def is_test(path: str) -> bool:
    """Check if file is a test file based on naming conventions."""
    filename = os.path.basename(path)
    for pattern in TEST_FILE_PATTERNS:
        if re.match(pattern, filename, re.IGNORECASE):
            return True
    return False

def get_category(path: str) -> str:
    """Get the general category of a file."""
    if is_image(path): return 'image'
    if is_video(path): return 'video'
    if is_audio(path): return 'audio'
    if is_archive(path): return 'archive'
    if is_document(path): return 'document'
    if is_code(path): return 'code'
    if is_test(path): return 'test'
    if is_binary(path): return 'binary'
    return 'text' if is_text(path) else 'unknown'

def guess_mime(path: str) -> str:
    """
    Guess MIME type based on extension and common mappings.
    """
    ext = get_extension(path)
    
    # Custom mappings for common types often missed or returned as weird types
    mime_map = {
        '.ts': 'application/typescript',
        '.tsx': 'application/typescript',
        '.jsx': 'application/javascript',
        '.md': 'text/markdown',
        '.yaml': 'text/yaml',
        '.yml': 'text/yaml',
        '.toml': 'text/toml',
        '.json': 'application/json',
        '.css': 'text/css',
        '.xyz': 'application/octet-stream',
    }
    
    if ext in mime_map:
        return mime_map[ext]

    # Standard library fallback
    mime, _ = mimetypes.guess_type(path)
    return mime or 'application/octet-stream'
