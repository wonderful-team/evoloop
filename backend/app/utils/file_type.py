"""
File Type Detection Utilities

Provides functions for detecting file types, checking if files are binary/text,
and identifying special file categories (test files, image files, etc.).
"""

import os
import re
from pathlib import Path

# Binary file extensions
BINARY_EXTENSIONS = {
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
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp',
    '.svg', '.ico', '.icns', '.raw', '.cr2', '.nef', '.heic',
}

# Video file extensions
VIDEO_EXTENSIONS = {
    '.mp4', '.avi', '.mov', '.wmv', '.flv', '.f4v', '.webm',
    '.mkv', '.m4v', '.3gp', '.mpg', '.mpeg', '.mpe', '.mpv',
}

# Audio file extensions
AUDIO_EXTENSIONS = {
    '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a',
    '.opus', '.aiff', '.au', '.ra', '.ram',
}

# Archive file extensions
ARCHIVE_EXTENSIONS = {
    '.zip', '.tar', '.gz', '.bz2', '.xz', '.7z', '.rar',
    '.tar.gz', '.tgz', '.tar.bz2', '.tar.xz', '.zipx',
}

# Document file extensions
DOCUMENT_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.odp', '.rtf', '.txt', '.md', '.csv',
}

# Code file extensions (common)
CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.c', '.cpp', '.cc', '.cxx',
    '.h', '.hpp', '.cs', '.go', '.rs', '.rb', '.php', '.swift', '.kt',
    '.scala', '.r', '.m', '.mm', '.pl', '.pm', '.lua', '.groovy',
    '.sql', '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
    '.html', '.htm', '.css', '.scss', '.sass', '.less', '.xml', '.json',
    '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.properties',
}

# Test file patterns
TEST_FILE_PATTERNS = [
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


def get_file_extension(file_path: str) -> str:
    """Get lowercase file extension including the dot."""
    return Path(file_path).suffix.lower()


def get_filename(file_path: str) -> str:
    """Get filename from path."""
    return os.path.basename(file_path)


def is_binary_file(file_path: str) -> bool:
    """
    Check if a file is likely binary based on extension.
    
    For files without known extensions, attempts to read the file
    and check for null bytes.
    
    Args:
        file_path: Path to the file
    
    Returns:
        True if file is likely binary
    """
    ext = get_file_extension(file_path)
    if ext in BINARY_EXTENSIONS:
        return True
    
    # If extension not in known list, try to detect by content
    if ext == '':
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(8192)
                # Check for null bytes (common in binary files)
                if b'\x00' in chunk:
                    return True
                # Check for high ratio of non-printable characters
                non_printable = sum(1 for b in chunk if b < 32 and b not in (9, 10, 13))
                if len(chunk) > 0 and non_printable / len(chunk) > 0.3:
                    return True
        except (IOError, OSError):
            return False
    
    return False


def is_text_file(file_path: str) -> bool:
    """
    Check if a file is likely a text file.
    
    Args:
        file_path: Path to the file
    
    Returns:
        True if file is likely text
    """
    return not is_binary_file(file_path)


def is_image_file(file_path: str) -> bool:
    """Check if file is an image."""
    return get_file_extension(file_path) in IMAGE_EXTENSIONS


def is_video_file(file_path: str) -> bool:
    """Check if file is a video."""
    return get_file_extension(file_path) in VIDEO_EXTENSIONS


def is_audio_file(file_path: str) -> bool:
    """Check if file is an audio file."""
    return get_file_extension(file_path) in AUDIO_EXTENSIONS


def is_archive_file(file_path: str) -> bool:
    """Check if file is an archive."""
    return get_file_extension(file_path) in ARCHIVE_EXTENSIONS


def is_document_file(file_path: str) -> bool:
    """Check if file is a document."""
    return get_file_extension(file_path) in DOCUMENT_EXTENSIONS


def is_code_file(file_path: str) -> bool:
    """Check if file is a code file."""
    ext = get_file_extension(file_path)
    filename = get_filename(file_path)
    
    if ext in CODE_EXTENSIONS:
        return True
    
    # Check shebang for scripts without extensions
    if ext == '':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
                if first_line.startswith('#!'):
                    return True
        except (IOError, OSError):
            pass
    
    return False


def is_test_file(file_path: str) -> bool:
    """
    Check if file is a test file based on naming conventions.
    
    Args:
        file_path: Path to the file
    
    Returns:
        True if file appears to be a test file
    """
    filename = get_filename(file_path)
    
    for pattern in TEST_FILE_PATTERNS:
        if re.match(pattern, filename, re.IGNORECASE):
            return True
    
    return False


def get_file_category(file_path: str) -> str:
    """
    Get the general category of a file.
    
    Returns one of: 'image', 'video', 'audio', 'archive', 'document',
    'code', 'test', 'binary', 'text', 'unknown'
    
    Args:
        file_path: Path to the file
    
    Returns:
        Category string
    """
    if is_image_file(file_path):
        return 'image'
    if is_video_file(file_path):
        return 'video'
    if is_audio_file(file_path):
        return 'audio'
    if is_archive_file(file_path):
        return 'archive'
    if is_document_file(file_path):
        return 'document'
    if is_code_file(file_path):
        return 'code'
    if is_test_file(file_path):
        return 'test'
    if is_binary_file(file_path):
        return 'binary'
    if is_text_file(file_path):
        return 'text'
    
    return 'unknown'


def guess_mime_type(file_path: str) -> str:
    """
    Guess MIME type based on file extension.
    
    Args:
        file_path: Path to the file
    
    Returns:
        MIME type string (e.g., 'image/jpeg', 'text/plain')
    """
    ext = get_file_extension(file_path)
    
    # Image types
    mime_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.tiff': 'image/tiff',
        '.tif': 'image/tiff',
        '.webp': 'image/webp',
        '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon',
        # Video types
        '.mp4': 'video/mp4',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.webm': 'video/webm',
        '.mkv': 'video/x-matroska',
        # Audio types
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.flac': 'audio/flac',
        '.ogg': 'audio/ogg',
        '.m4a': 'audio/mp4',
        # Document types
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        # Code types
        '.py': 'text/x-python',
        '.js': 'application/javascript',
        '.ts': 'application/typescript',
        '.json': 'application/json',
        '.xml': 'application/xml',
        '.html': 'text/html',
        '.css': 'text/css',
        '.md': 'text/markdown',
        '.txt': 'text/plain',
        # Archive types
        '.zip': 'application/zip',
        '.tar': 'application/x-tar',
        '.gz': 'application/gzip',
        '.bz2': 'application/x-bzip2',
        '.7z': 'application/x-7z-compressed',
    }
    
    return mime_map.get(ext, 'application/octet-stream')
