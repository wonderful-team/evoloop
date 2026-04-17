"""
Preference Priming - Loads user preferences during awakening.
"""

import logging

from app.core.environment.models import PreferenceContext

logger = logging.getLogger(__name__)


async def prime_preferences(project_id: int | None = None) -> PreferenceContext:
    """
    Load user preferences.

    Args:
        project_id: Optional project ID to scope preference retrieval.

    Returns:
        PreferenceContext with user preferences.
    """
    # Retrieve user preferences from Preference Store
    from app.core.memory.lifespan import MemoryLifespanManager
    from app.infrastructure.config.service import SystemConfigService

    user_id = 1  # Default user

    if not MemoryLifespanManager.is_initialized():
        await MemoryLifespanManager.ainitialize()
    container = MemoryLifespanManager.get_container()
    manager = container.memory_manager
    prefs_text = await manager.get_merged_preferences(
        user_id=user_id,
        project_id=project_id,
    )
    preferences = _parse_preferences(prefs_text)

    # Add language preference
    language = SystemConfigService.get_language_preference()
    if language:
        preferences["language"] = language

    return PreferenceContext(preferences=preferences)


def _parse_preferences(raw_text: str) -> dict[str, str]:
    """Parse preference text into key-value pairs."""
    prefs = {}

    if not raw_text:
        return prefs

    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Try to split on colon or equals
        for sep in [":", "="]:
            if sep in line:
                key, value = line.split(sep, 1)
                prefs[key.strip().lower().replace(" ", "_")] = value.strip()
                break

    return prefs
