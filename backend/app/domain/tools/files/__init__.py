"""
File Management Tools - Agent-Friendly Collection

This module exports specialized file tools optimized for Agent cognition:
- read_file: Read file contents
- grep_search: Search text patterns in files
- find_files: Find files by pattern
- write_file: Create or overwrite files
- edit_file: Edit files with preview support
- list_dir: List directory contents (tree or flat)
- move_file: Rename or move files safely with Rewind support
- delete_file: Delete files safely with Rewind support
"""

from .edit_file import edit_file
from .list_dir import list_dir
from .read_file import read_file
from .write_file import write_file
from .move_file import move_file
from .delete_file import delete_file
from .grep_search import grep_search
from .find_files import find_files

__all__ = [
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "move_file",
    "delete_file",
    "grep_search",
    "find_files",
]
