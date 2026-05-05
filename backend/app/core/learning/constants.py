from app.core.learning.schemas import ActionCategory

# Mapping of generic event types to high-level categories
EVENT_CATEGORY_MAP = {
    "tool_call": ActionCategory.QUERY,  # Default, refined by tool-specific map
    "click": ActionCategory.INTERACTION,
    "input": ActionCategory.INTERACTION,
    "node_start": ActionCategory.OTHER,
    "llm_output": ActionCategory.DECISION,
}

# Tool-specific category overrides
TOOL_CATEGORY_MAP = {
    "read_file": ActionCategory.QUERY,
    "write_file": ActionCategory.EDIT,
    "edit_file": ActionCategory.EDIT,
    "search_files": ActionCategory.QUERY,
    "list_directory": ActionCategory.QUERY,
    "search_codebase": ActionCategory.QUERY,
    "search_web": ActionCategory.QUERY,
    "execute_command": ActionCategory.COMMAND,
    "git_operations": ActionCategory.COMMAND,
    "navigate_directory": ActionCategory.NAVIGATION,
    "mobile_control": ActionCategory.SYSTEM_INTERACTION,
    "desktop_control": ActionCategory.SYSTEM_INTERACTION,
}
