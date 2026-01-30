"""Preference management interface for hierarchical user settings."""

from abc import abstractmethod
from typing import Optional

from app.core.memory.interfaces.base import IMemoryProvider


class IPreferenceStore(IMemoryProvider):
    """
    Interface for managing user preferences with hierarchical scoping.
    Supports global preferences with project-specific overrides.
    """

    @abstractmethod
    async def set_preference(
        self,
        user_id: str,
        key: str,
        value: str,
        description: str = "",
        project_id: Optional[int] = None,
    ) -> None:
        """
        Set a user preference.

        Args:
            user_id: User identifier
            key: Preference key
            value: Preference value
            description: Optional description of the preference
            project_id: If None, sets global preference. If provided, sets project-specific preference.
        """
        pass

    @abstractmethod
    async def get_merged_preferences(self, user_id: str, project_id: Optional[int] = None) -> str:
        """
        Get merged preferences with project overrides.

        Args:
            user_id: User identifier
            project_id: Project context. If provided, project preferences override global ones.

        Returns:
            Formatted string of merged preferences
        """
        pass
