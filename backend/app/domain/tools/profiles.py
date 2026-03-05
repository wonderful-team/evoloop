from langchain_core.tools import BaseTool

# Define Standard Profiles
# These are "Presets" that the Supervisor can select to prime the Coder with the right tools.

PROFILES: dict[str, dict[str, any]] = {
    "GENERAL": {
        "description": "General purpose coding and file management.",
        "static_tools": [
            "read_file",
            "write_file",
            "edit_file",
            "list_files",
            "file_system",
            "explore_codebase",
            "manage_git",
            "bash",
            "manage_memory",
            "consult_architecture",
            "consult_lsp",
        ],
        "retrieval_query": "general software development",
    },
    "DEVOPS": {
        "description": "Infrastructure, Deployment, Docker, Kubernetes.",
        "static_tools": [
            "read_file",
            "write_file",
            "edit_file",
            "list_files",
            "bash",
            "manage_git",
        ],  # Base tools
        "retrieval_query": "kubernetes docker helm aws cloud operations",
    },
    "RESEARCH": {
        "description": "Deep analysis, reading docs, exploring broad concepts.",
        "static_tools": [
            "read_file",
            "list_files",
            "explore_codebase",
            "consult_architecture",
            "manage_memory",
        ],
        "retrieval_query": "documentation research analysis",
    },
}


def get_profile_static_tools(profile_name: str) -> list[BaseTool]:
    """Retrieve the static tool instances for a given profile."""
    from app.core.tools.registry import get_tools_by_names

    profile = PROFILES.get(profile_name, PROFILES["GENERAL"])
    tool_names = profile.get("static_tools", [])
    return get_tools_by_names(tool_names)


def get_profile_query(profile_name: str) -> str:
    """Retrieve the default retrieval query for a profile."""
    profile = PROFILES.get(profile_name, PROFILES["GENERAL"])
    return profile.get("retrieval_query", "")
