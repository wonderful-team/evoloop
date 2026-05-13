"""
Domain Tools - Tool collection for the EvoLoop agent system.

This module organizes tools by functionality:
- files: File operations (read, write, edit, search)
- environment: UI automation (browser, desktop, mobile)
- learning: Skill and knowledge management
- coding: Code analysis and LSP integration
"""

# Import submodules to ensure tools are registered

# Import sub-packages
from app.domain.tools import (
    coding,  # LSP internal classes (not tools)
    environment,
    files,
    learning,
)

__all__ = [
    # Sub-packages
    "files",
    "environment",
    "learning",
    "coding",
]
