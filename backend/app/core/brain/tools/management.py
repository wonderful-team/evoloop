"""
Explicit Memory Management Tools.
Allows the Supervisor to manually control its Focus (Core Memory) and Journal (Archival Memory).
"""
import logging
import os
from datetime import datetime
from langchain_core.tools import tool
from app.core.config import settings
from app.core.brain.filesystem.manager import BrainFileSystem

logger = logging.getLogger(__name__)

@tool
async def update_focus(content: str) -> str:
    """
    Overwrites the 'Current Focus' section of your memory (Core Memory).
    Use this to persist your high-level goal, plan status, or critical constraints across steps.
    This content will be always visible in your system prompt.
    """
    try:
        fs = BrainFileSystem(settings.BRAIN_MEMORY_ROOT)
        # Writes to /working/focus.md - "Core Memory"
        path = "working/focus.md"
        fs.write_file(path, content)
        return "Core Memory (Focus) updated."
    except Exception as e:
        logger.error(f"Failed to update focus: {e}")
        return f"Error updating focus: {e}"

@tool
async def memorize(content: str, category: str = "fact") -> str:
    """
    Explicitly saves a fact to Long-term Memory (Journal) immediately.
    Use this for critical information you cannot afford to lose (e.g. user preferences, critical design decisions).
    """
    try:
        fs = BrainFileSystem(settings.BRAIN_MEMORY_ROOT)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n[{timestamp}] [{category.upper()}] {content}"
        path = "knowledge/journal.md"
        fs.append_file(path, entry)
        return "Fact saved to Archival Memory."
    except Exception as e:
        logger.error(f"Failed to memorize: {e}")
        return f"Error saving fact: {e}"
