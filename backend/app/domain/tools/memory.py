from langchain_core.tools import tool
from app.domain.memory.service import memory_service

@tool
async def save_preference(key: str, value: str, description: str = "", is_global: bool = False, project_id: int = 1):
    """
    Save a user preference or instruction to long-term memory.
    
    Args:
        key: A short, unique key (e.g., "test_framework").
        value: The value (e.g., "pytest").
        description: Optional context.
        is_global: If True, applies to ALL projects. If False (default), applies only to current project.
        project_id: Current project ID.
    """
    pid = None if is_global else project_id
    await memory_service.add_user_preference("user_default", key, value, description, project_id=pid)
    scope_str = "Global" if is_global else f"Project {project_id}"
    return f"Preference saved ({scope_str}): {key}={value}"

@tool
async def get_user_preferences(project_id: int = 1):
    """
    Retrieve all current user preferences, merging global defaults with project-specific overrides.
    
    Args:
        project_id: Current project ID.
    """
    prefs = await memory_service.get_user_preferences("user_default", project_id=project_id)
    return f"Current Preferences (Project {project_id}):\n{prefs}"

@tool
async def search_concepts(query: str, project_id: int = 1):
    """
    Search the project's Concept Graph for definitions of terms, architecture components, or specific project "jargon".
    Use this when you encounter a term you don't understand or want to know the role of a specific component.
    
    Args:
        query: The search term (e.g., "Evoloop Protocol", "Orchestrator").
        project_id: The ID of the project to search in. Default to 1 (current).
    """
    return await memory_service.search_concepts(query, project_id)

@tool
async def add_concept(name: str, description: str, project_id: int = 1):
    """
    Add a new concept or term to the Project's Knowledge Graph.
    
    Args:
        name: The name of the concept (e.g., "Shadow DOM").
        description: A concise definition or description of the concept in the context of this project.
        project_id: The ID of the project. Default to 1 (current).
    """
    await memory_service.add_concept(name, description, project_id)
    return f"Concept added: {name}"
