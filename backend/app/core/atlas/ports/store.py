from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from app.core.atlas.models import AtlasApp

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
    async def get_app_summary(self, bundle_id: str, platform: str = "macos") -> Optional[Dict[str, Any]]:
        """
        Retrieve a summary of the application, including known states and elements.
        Used for LLM context generation.
        """
        pass

    @abstractmethod
    async def get_state_detail(self, bundle_id: str, state_id: str, platform: str = "macos") -> Optional[Dict[str, Any]]:
        """
        Retrieve detailed information about a specific UI state, including its elements.
        """
        pass

    @abstractmethod
    async def list_apps(self) -> List[Dict[str, Any]]:
        """
        List all applications currently mapped in the Atlas.
        """
        pass
