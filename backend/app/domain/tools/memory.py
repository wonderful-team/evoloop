from langchain_core.tools import tool

from app.core.memory import memory_manager
from app.logging import get_context


@tool
async def save_preference(
    key: str,
    value: str,
    description: str = "",
    is_global: bool = False,
    project_id: int = None,
):
    """
    Save a user preference or instruction to long-term memory.

    Args:
        key: A short, unique key (e.g., "test_framework").
        value: The value (e.g., "pytest").
        description: Optional context.
        is_global: If True, applies to ALL projects. If False (default), applies only to current project.
        project_id: Current project ID. Optional, defaults to current context.
    """
    ctx_pid = get_context().get("project_id", 1)
    pid = project_id or ctx_pid

    target_pid = None if is_global else pid
    await memory_manager.preferences.set_preference("user_default", key, value, description, project_id=target_pid)
    scope_str = "Global" if is_global else f"Project {target_pid}"
    return f"Preference saved ({scope_str}): {key}={value}"


@tool
async def get_user_preferences(project_id: int = None):
    """
    Retrieve all current user preferences, merging global defaults with project-specific overrides.

    Args:
        project_id: Current project ID. Optional, defaults to current context.
    """
    ctx_pid = get_context().get("project_id", 1)
    pid = project_id or ctx_pid
    prefs = await memory_manager.preferences.get_merged_preferences("user_default", project_id=pid)
    return f"Current Preferences (Project {pid}):\n{prefs}"


@tool
async def search_concepts(query: str, project_id: int = None):
    """
    Search the project's Concept Graph.

    Args:
        query: The search term.
        project_id: The ID of the project to search in. Optional.
    """
    ctx_pid = get_context().get("project_id", 1)
    pid = project_id or ctx_pid
    results = await memory_manager.long_term.search_concepts(query, pid)
    if not results:
        return "No relevant concepts found."
    lines = []
    for r in results:
        scope = "[Global]" if r.score == 0 else ""
        files_str = ""
        if r.files:
            basenames = [f.split("/")[-1] for f in r.files]
            files_str = f"\n  Related Files: {', '.join(basenames)}"
        lines.append(f"- **{r.name}** {scope} (Score: {r.score:.2f}): {r.description}{files_str}")
    return "\n".join(lines)


@tool
async def add_concept(name: str, description: str, project_id: int = None):
    """
    Add a new concept or term to the Project's Knowledge Graph.

    Args:
        name: The name of the concept.
        description: A concise definition.
        project_id: The ID of the project. Optional.
    """
    ctx_pid = get_context().get("project_id", 1)
    pid = project_id or ctx_pid
    from app.core.memory.interfaces.long_term import Concept
    concept = Concept(name, description, pid)
    await memory_manager.long_term.store_concept(concept)
    return f"Concept added: {name}"
