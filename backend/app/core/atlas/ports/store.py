from abc import ABC, abstractmethod
from typing import Any

from app.core.atlas.models import AtlasApp
from app.core.atlas.schemas import AtlasAppSummary, AtlasStateDetail, AtlasAppInfo


class IAtlasStore(ABC):
    """
    Port interface for App Atlas persistence.
    Adapters (e.g. Neo4jAtlasStore, JsonAtlasStore) must implement this.
    """

    @abstractmethod
    async def save_app_model(self, atlas_app: AtlasApp) -> None:
        """
        Save or update an application map.
        """
        pass

    @abstractmethod
    async def get_app_summary(self, bundle_id: str, platform: str = "macos") -> AtlasAppSummary | None:
        """
        Retrieve a summary of the application, including known states and elements.
        Used for LLM context generation.
        """
        pass

    @abstractmethod
    async def get_state_detail(self, bundle_id: str, state_id: str, platform: str = "macos") -> AtlasStateDetail | None:
        """
        Retrieve detailed information about a specific UI state, including its elements.
        """
        pass

    @abstractmethod
    async def get_transitions_summary(self, bundle_id: str, platform: str = "macos") -> list[dict[str, Any]]:
        """
        Retrieve a summary of all transitions for an application.
        """
        pass

    @abstractmethod
    async def list_apps(self) -> list[AtlasAppInfo]:
        """
        List all applications currently mapped in the Atlas.
        """
        pass

    @abstractmethod
    async def clear_all_data(self) -> None:
        """
        Permanently deletes all Atlas data (Apps, States, Transitions).
        """
        pass
