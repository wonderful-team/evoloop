from app.core.context.manager import ContextManager
from app.core.memory import memory_manager
from app.core.tools import evoloop_tool


@evoloop_tool(
    is_state_mutating=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.manage_memory",
    name_map={"zh": "保存偏好", "en": "Save Preference"}
)
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
    ctx = ContextManager.current()
    pid = project_id or ctx.project_id or 1

    target_pid = None if is_global else pid
    await memory_manager.preferences.set_preference("user_default", key, value, description, project_id=target_pid)
    scope_str = "Global" if is_global else f"Project {target_pid}"
    return f"Preference saved ({scope_str}): {key}={value}"


@evoloop_tool(
    is_pollable=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.manage_memory",
    name_map={"zh": "获取用户偏好", "en": "Get User Preferences"}
)
async def get_user_preferences(project_id: int = None):
    """
    Retrieve all current user preferences, merging global defaults with project-specific overrides.

    Args:
        project_id: Current project ID. Optional, defaults to current context.
    """
    ctx = ContextManager.current()
    pid = project_id or ctx.project_id or 1
    prefs = await memory_manager.preferences.get_merged_preferences("user_default", project_id=pid)
    return f"Current Preferences (Project {pid}):\n{prefs}"


@evoloop_tool(
    is_pollable=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.manage_memory",
    name_map={"zh": "搜索概念", "en": "Search Concepts"}
)
async def search_concepts(query: str, project_id: int = None):
    """
    Search the project's Concept Graph.

    Args:
        query: The search term.
        project_id: The ID of the project to search in. Optional.
    """
    ctx = ContextManager.current()
    pid = project_id or ctx.project_id or 1
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


@evoloop_tool(
    is_state_mutating=True,
    is_memory_tool=True,
    summary_template="database_logger.tool_summary.manage_memory",
    name_map={"zh": "添加概念", "en": "Add Concept"}
)
async def add_concept(name: str, description: str, project_id: int = None):
    """
    Add a new concept or term to the Project's Knowledge Graph.

    Args:
        name: The name of the concept.
        description: A concise definition.
        project_id: The ID of the project. Optional.
    """
    ctx = ContextManager.current()
    pid = project_id or ctx.project_id or 1
    from app.core.memory.interfaces.long_term import Concept
    concept = Concept(name, description, pid)
    await memory_manager.long_term.store_concept(concept)
    return f"Concept added: {name}"
