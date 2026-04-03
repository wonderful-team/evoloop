"""
Memory tool implementations - internal use only.

These functions are used by the manage_memory facade tool.
They are NOT exposed as standalone tools to avoid duplication.
"""
import logging

from app.core.context.manager import ContextManager
from app.utils import ProjectManagementFormatter

logger = logging.getLogger(__name__)


async def save_preference_impl(
    key: str,
    value: str,
    description: str = "",
    is_global: bool = False,
    project_id: int = None,
) -> str:
    """Save a user preference or instruction to long-term memory."""
    from app.core.memory import MemoryContainer, MemoryConfig

    ctx = ContextManager.current()
    pid = project_id or ctx.project_id or 1

    target_pid = None if is_global else pid

    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    try:
        manager = container.memory_manager
        await manager.preferences.set_preference("user_default", key, value, description, project_id=target_pid)
        scope_str = "Global" if is_global else f"Project {target_pid}"
        return f"Preference saved ({scope_str}): {key}={value}"
    finally:
        await container.shutdown()


async def get_user_preferences_impl(project_id: int = None) -> str:
    """Retrieve all current user preferences."""
    from app.core.memory import MemoryContainer, MemoryConfig

    ctx = ContextManager.current()
    pid = project_id or ctx.project_id or 1

    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    try:
        manager = container.memory_manager
        prefs = await manager.preferences.get_merged_preferences("user_default", project_id=pid)
        return f"Current Preferences (Project {pid}):\n{prefs}"
    finally:
        await container.shutdown()


async def search_concepts_impl(query: str, project_id: int = None) -> str:
    """Search the project's Concept Graph."""
    from app.core.memory import MemoryContainer, MemoryConfig

    ctx = ContextManager.current()
    pid = project_id or ctx.project_id or 1

    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    try:
        manager = container.memory_manager
        results = await manager.long_term.search_concepts(query, pid)
        if not results:
            return "No relevant concepts found."
        try:
            return ProjectManagementFormatter.concepts(results)
        except Exception as e:
            logger.error(f"Failed to render concepts: {e}")
            return f"Found {len(results)} concepts."
    finally:
        await container.shutdown()


async def add_concept_impl(name: str, description: str, project_id: int = None) -> str:
    """Add a new concept or term to the Project's Knowledge Graph."""
    from app.core.memory import MemoryContainer, MemoryConfig
    from app.core.memory.interfaces.long_term import Concept

    ctx = ContextManager.current()
    pid = project_id or ctx.project_id or 1

    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    try:
        manager = container.memory_manager
        concept = Concept(name, description, pid)
        await manager.long_term.store_concept(concept)
        return f"Concept added: {name}"
    finally:
        await container.shutdown()


async def find_related_episodes_impl(concept_name: str, project_id: int = None) -> str:
    """Find historical tasks related to a concept."""
    from app.core.memory import MemoryContainer, MemoryConfig

    ctx = ContextManager.current()
    pid = project_id or ctx.project_id or 1

    container = MemoryContainer(MemoryConfig.from_settings())
    await container.initialize()
    try:
        manager = container.memory_manager
        episodes = await manager.long_term.find_episodes_by_concept(concept_name, pid)
        if not episodes:
            return f"No historical episodes found related to '{concept_name}'."
        try:
            return ProjectManagementFormatter.episodes(episodes)
        except Exception as e:
            logger.error(f"Failed to render episodes list: {e}")
            return f"Found {len(episodes)} episodes."
    finally:
        await container.shutdown()
