"""
Domain Tools - Tool collection for the EvoLoop agent system.

This module organizes tools by functionality:
- files: File operations (read, write, edit, search)
- environment: UI automation (browser, desktop, mobile)
- learning: Skill and knowledge management
- coding: Code analysis and LSP integration
"""

# Import submodules to ensure tools are registered
from app.domain.tools import (
    atlas,
    checkpoint_tools,
    document_reader,
    dynamic,
    execution,
    facades,
    ghost_text,
    human_input,
    knowledge,
    mcp_manager,
    memory_tools,
    project_tools,
    research,
    scheduler,
    todo_tools,
    vision,
    wiki_tools,
    workspace_tools,
)

# Import sub-packages
from app.domain.tools import (
    coding,  # LSP internal classes (not tools)
    environment,
    files,
    learning,
)

# Import codebase exploration tools (replaces consult_lsp, explore_codebase, search_files)
from app.domain.codebase.exploration import (
    find_symbol,
    search_code,
    ask_codebase,
    analyze_impact,
    check_types,
    inspect_symbol,
)

__all__ = [
    # Sub-packages
    "files",
    "environment",
    "learning",
    "coding",
]
