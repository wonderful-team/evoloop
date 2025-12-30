import logging
import os
import re
from pathlib import Path
from typing import Tuple, List, Optional

try:
    from rapidfuzz import process, fuzz
except ImportError:
    pass

from app.domain.codebase.constants import (
    DEFAULT_EXCLUDED_FILES, 
    DEFAULT_EXCLUDED_DIRS,
    BLACKLIST_FILE_EXTENSIONS,
    WHITELIST_FILE_EXTENSIONS,
    BLACKLIST_DIRS,
    BLACKLIST_FILES,
    CODE_EXTENSION_MAP
)

def get_directory_size(path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def get_file_contents(file_path: str, encode=False):
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            if encode:
                return f.read().encode()
            return f.read()
        except UnicodeDecodeError:
            logging.warning("Unable to decode file %s.", file_path)
            return None


def write_file_contents(content: str, file_path: str):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logging.info(f"Writing file {file_path} completed")
    except Exception as e:
        raise ValueError(f"Failed to write file: {e}")


def create_file_if_not_exists(file_path: str):
    if not os.path.exists(file_path):
        with open(file_path, "w") as f:
            f.write("")


def open_text_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            f.read(1024)
        return True
    except UnicodeDecodeError:
        return False


def is_encrypted_path(file_path: str, pattern=r'[a-f0-9]{8,}'):
    # Check if any part of path looks like a hash (common in build artifacts but not always encrypted)
    # This was in engineer code.
    for part in Path(file_path).parts:
        if re.search(pattern, part):
            return True
    return False


def load_files(dir_path: str):
    file_list = []

    for root, dirs, files in os.walk(dir_path):
        if any(blacklist in root for blacklist in BLACKLIST_DIRS):
            continue
        for file in files:
            file_ext = get_file_ext(file)
            if any(whitelist == file_ext for whitelist in WHITELIST_FILE_EXTENSIONS):
                if file not in BLACKLIST_FILES:
                    file_list.append(os.path.join(root, file))

    return file_list


def get_file_ext(file):
    return os.path.splitext(file)[1].lower()


def get_file_mtime(filename):
    try:
        return os.path.getmtime(filename)
    except FileNotFoundError:
        logging.error(f"File not found error: {filename}")


def change_dir(path):
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)


def get_file_encoding(file_path: str) -> str:
    """
    Attempt to detect file encoding
    """
    encodings = ['utf-8', 'latin-1', 'utf-16', 'ascii']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read(100) 
                return encoding
        except UnicodeDecodeError:
            continue

    return 'utf-8'


def read_file_content(file_path: str) -> Tuple[str, str]:
    """
    Read file content with auto encoding detection
    """
    encoding = get_file_encoding(file_path)

    try:
        with open(file_path, 'r', encoding=encoding) as f:
            content = f.read()
        return content, encoding
    except Exception as e:
        logging.error(f"Failed to read file: {file_path}, error: {str(e)}")
        return "", encoding


def filter_code_files(
    all_files: List[str],
    excluded_dirs: List[str] = None,
    excluded_files: List[str] = None,
    include_extensions: List[str] = None
) -> List[str]:
    """
    Filter code files
    """
    if excluded_dirs is None:
        excluded_dirs = DEFAULT_EXCLUDED_DIRS

    if excluded_files is None:
        excluded_files = DEFAULT_EXCLUDED_FILES

    code_files = []

    for file_path in all_files:
        # Check excluded dirs
        if any(f"/{excluded_dir}/" in f"/{file_path}/" for excluded_dir in excluded_dirs):
            continue

        # Check excluded files
        if any(file_path.endswith(excluded_file) for excluded_file in excluded_files):
            continue

        ext = get_file_ext(file_path)

        # Check extensions
        if include_extensions:
            if ext and ext[1:] in include_extensions:
                code_files.append(file_path)
                continue

        # Default check code extension
        if ext in CODE_EXTENSION_MAP:
            code_files.append(file_path)

    return code_files


def is_text_file(file_path):
    file_ext = get_file_ext(file_path)
    if file_ext in BLACKLIST_FILE_EXTENSIONS:
        return False
    elif file_ext in WHITELIST_FILE_EXTENSIONS or open_text_file(file_path):
        return True
    else:
        return False


def is_binary_file(file_path: str) -> bool:
    """Check if file is binary"""
    binary_extensions = {
        '.pyc', '.so', '.dll', '.exe', '.bin', '.jpg', '.jpeg', '.png',
        '.gif', '.bmp', '.ico', '.pdf', '.zip', '.tar', '.gz', '.tgz',
        '.rar', '.7z', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
        '.class', '.jar', '.war', '.ear', '.o', '.a', '.lib', '.mp3',
        '.mp4', '.avi', '.mov', '.flv', '.wmv', '.wma', '.ttf', '.db'
    }

    ext = get_file_ext(file_path)
    if ext.lower() in binary_extensions:
        return True

    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(4096)

        if b'\x00' in chunk:
            return True

        try:
            chunk.decode('utf-8')
        except UnicodeDecodeError:
            return True

        non_ascii_chars = sum(1 for b in chunk if b < 32 and b != 9 and b != 10 and b != 13)
        if len(chunk) > 0 and non_ascii_chars / len(chunk) > 0.3:
            return True

        return False

    except (IOError, OSError):
        logging.warning(f"Cannot read file to detect type: {file_path}")
        return True

    except Exception as e:
        logging.error(f"Error checking binary file: {file_path}, error: {str(e)}")
        return True


def normalize_path(path: str) -> str:
    path = path.replace('\\', '/')
    path = path.lstrip('/')
    return path


def resolve_path(file_path: str, local_path: str, repo_files: List[str]) -> Optional[str]:
    """Resolve file path to full path"""
    if not file_path:
        return None

    if os.path.isabs(file_path) and os.path.exists(file_path):
        return file_path

    full_path = os.path.join(local_path, file_path)
    if os.path.exists(full_path):
        return full_path

    repo_parts = local_path.split(os.path.sep)
    file_parts = file_path.split('/')

    if file_parts and repo_parts and file_parts[0] == repo_parts[-1]:
        adjusted_path = os.path.join(local_path, *file_parts[1:])
        if os.path.exists(adjusted_path):
            return adjusted_path

    for repo_file in repo_files:
        if repo_file == file_path:
            return os.path.join(local_path, repo_file)

        if repo_file.endswith(file_path):
            full_repo_path = os.path.join(local_path, repo_file)
            if os.path.exists(full_repo_path):
                return full_repo_path

        if os.path.basename(repo_file) == os.path.basename(file_path):
            full_repo_path = os.path.join(local_path, repo_file)
            if os.path.exists(full_repo_path):
                return full_repo_path

    similar_file = find_similar_file(file_path, repo_files)
    if similar_file:
        return os.path.join(local_path, similar_file)

    logging.warning(f"Could not resolve path: {file_path}")
    return None


def find_similar_file(file_path: str, repo_files: List[str], threshold: float = 0.7) -> Optional[str]:
    """
    Find similar file using fuzzy matching
    """
    try:
        matches = process.extractOne(
            file_path,
            repo_files,
            scorer=fuzz.WRatio
        )

        if matches and matches[1] >= threshold * 100:
            logging.debug(f"Fuzzy match '{file_path}' -> '{matches[0]}' (Score: {matches[1]}%)")
            return matches[0]

        filename = os.path.basename(file_path)
        if filename != file_path:
            all_filenames = [os.path.basename(f) for f in repo_files]
            filename_to_path = {os.path.basename(f): f for f in repo_files}

            matches = process.extractOne(
                filename,
                all_filenames,
                scorer=fuzz.WRatio
            )

            if matches and matches[1] >= threshold * 100:
                matched_file = filename_to_path[matches[0]]
                logging.debug(f"Filename fuzzy match '{filename}' -> '{matches[0]}' (Score: {matches[1]}%)")
                return matched_file

        return None
    except NameError:
        logging.debug("rapidfuzz not installed, using simple match")
        for repo_file in repo_files:
            if file_path.lower() in repo_file.lower():
                return repo_file
        return None
