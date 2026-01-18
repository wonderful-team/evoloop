"""
File Management Tools - Atomic Tool Collection

This module exports 5 specialized file tools, replacing the monolithic manage_file.
"""
from .read_file import read_file
from .write_file import write_file
from .edit_file import edit_file
from .list_files import list_files
from .file_system import file_system

# Deprecated: Keep manage_file for backward compatibility (will be removed in future)
from .dispatcher import manage_file

__all__ = [
    "read_file",
    "write_file",
    "edit_file",
    "list_files",
    "file_system",
    "manage_file",  # Deprecated
]
