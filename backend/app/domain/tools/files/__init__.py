"""
File Management Tools - Agent-Friendly Collection

This module exports specialized file tools optimized for Agent cognition:
- read_file: Read file contents
- search_files: Search text patterns in files  
- write_file: Create or overwrite files
- edit_file: Edit files with preview support
- multiedit_file: Edit multiple parts of a file atomically
- list_directory: List directory contents (tree or flat)
- manage_directory: Manage directories (mkdir, delete, move)
"""

from .apply_patch_file import apply_patch_file
from .edit_file import edit_file
from .list_directory import list_directory, manage_directory
from .multiedit_file import multiedit_file
from .read_file import read_file
from .search_files import search_files
from .write_file import write_file

__all__ = [
    "apply_patch_file",
    "read_file",
    "write_file", 
    "edit_file",
    "multiedit_file",
    "search_files",
    "list_directory",
    "manage_directory",
]
