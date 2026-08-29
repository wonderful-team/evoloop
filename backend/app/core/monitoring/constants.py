"""Monitoring / HITL constants."""

#: Standardized global-mode restriction messages by tool category.
GLOBAL_MODE_MESSAGES = {
    "code_search": "[Workspace Mode]: Code search requires a project. Please provide a project_id or switch to a project.",
    "wiki": "[Workspace Mode]: Wiki requires a project.",
    "architecture": "[Workspace Mode]: Architecture consultation requires a project.",
    "file_operation": "[Workspace Mode]: File operations require a project.",
    "git": "[Workspace Mode]: Git operations require a project.",
    "default": "[Workspace Mode]: This operation requires a specific project.",
}
