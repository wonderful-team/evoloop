from langchain_core.tools import tool
from app.domain.memory.service import memory_service

@tool
async def save_preference(key: str, value: str, description: str = ""):
    """
    Save a user preference or instruction to long-term memory.
    Use this when the user explicitly gives an instruction about how they want things done (e.g., "Always use pytest", "Don't use X library").
    
    Args:
        key: A short, unique key for the preference (e.g., "test_framework", "logging_library").
        value: The value or instruction (e.g., "pytest", "loguru").
        description: Optional context or full instruction (e.g., "User prefers pytest over unittest").
    """
    await memory_service.add_user_preference("user_default", key, value, description)
    return f"Preference saved: {key}={value}"

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
