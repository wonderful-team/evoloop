"""
File System Memory Protocol.

Defines the schema and standard paths for the agent's file memory.
"""

from enum import Enum
from pathlib import Path

class MemoryZone(str, Enum):
    SYS = "sys"
    WORKING = "working"
    KNOWLEDGE = "knowledge"
    LOGS = "logs"

class MemoryFile(str, Enum):
    # System
    IDENTITY = "identity.md"
    TOOLS = "tools.md"
    RULES = "rules.md"
    
    # Working
    TASK = "current_task.md"
    SCRATCHPAD = "scratchpad.md"
    
    # Knowledge (Directories)
    PROJECTS = "projects"
    USERS = "users"

# Directory Structure Template
DEFAULT_STRUCTURE = {
    MemoryZone.SYS: [MemoryFile.IDENTITY, MemoryFile.TOOLS, MemoryFile.RULES],
    MemoryZone.WORKING: [MemoryFile.TASK, MemoryFile.SCRATCHPAD],
    MemoryZone.KNOWLEDGE: [MemoryFile.PROJECTS, MemoryFile.USERS],
    MemoryZone.LOGS: []
}

def get_zone_path(root: Path, zone: MemoryZone) -> Path:
    return root / zone.value
