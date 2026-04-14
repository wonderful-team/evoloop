"""
Domain Tools - Tool collection for the EvoLoop agent system.

This module organizes tools by functionality:
- files: File operations (read, write, edit, search)
- environment: UI automation (browser, desktop, mobile)
- learning: Skill and knowledge management
- coding: Code analysis and LSP integration
"""

# Import submodules to ensure tools are registered

# Todo tools are now part of the todo domain module

# Import sub-packages
from app.domain.tools import (
    coding,  # LSP internal classes (not tools)
    environment,
    files,
    learning,
)

# Import codebase exploration tools (replaces consult_lsp, explore_codebase)

# Import search_code from files (search_code is an alias for search_files)
from app.domain.tools.files import search_files as search_code

__all__ = [
    # Sub-packages
    "files",
    "environment",
    "learning",
    "coding",
]
