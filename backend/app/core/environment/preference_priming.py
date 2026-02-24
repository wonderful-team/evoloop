"""
Preference Priming - Loads user preferences and system rules during awakening.
"""

import logging

from app.core.environment.models import PreferenceContext

logger = logging.getLogger(__name__)


async def prime_preferences(project_id: int | None = None) -> PreferenceContext:
    """
    Load user preferences and system rules.
    
    Args:
        project_id: Optional project ID to scope preference retrieval.
        
    Returns:
        PreferenceContext with preferences and rules.
    """
    preferences = {}

    # 1. Retrieve user preferences from Preference Store
    try:
        from app.core.memory import memory_manager
        from app.infrastructure.config.service import SystemConfigService

        user_id = 1  # Default user
        prefs_text = await memory_manager.preferences.get_merged_preferences(
            user_id=user_id,
            project_id=project_id,
        )
        preferences = _parse_preferences(prefs_text)

        # Add language preference
        language = SystemConfigService.get_language_preference()
        if language:
            preferences["language"] = language

    except Exception as e:
        logger.warning(f"Failed to retrieve preferences: {e}")

    # 2. System-level inviolable rules (hardcoded for safety)
    # Critical rules (always shown, high severity)
    critical_rules = [
        "NEVER delete .git directories or any version control metadata",
        "NEVER execute 'rm -rf /' or any recursive deletion commands targeting root or system directories",
        "NEVER execute DROP, TRUNCATE, or DELETE operations on production databases without confirmation",
        "NEVER expose, log, or print API keys, passwords, tokens, or any sensitive credentials",
    ]

    # Important rules (shown when space permits)
    important_rules = [
        "NEVER modify core dependency versions in package.json or requirements.txt without explicit user confirmation",
        "ALWAYS create backups before making significant changes to critical files",
        "ALWAYS verify the scope of file deletions before execution",
        "ALWAYS ask for clarification when user intent is ambiguous or destructive",
    ]

    rules = critical_rules + important_rules

    return PreferenceContext(preferences=preferences, rules=rules)


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
