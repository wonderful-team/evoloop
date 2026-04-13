from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict
from app.utils.model_helpers import LegacyDictMixin
from app.core.atlas.models import AtlasApp


class AtlasAppSummary(BaseModel, LegacyDictMixin):
    """Summary of an Atlas app for LLM context generation."""
    model_config = ConfigDict(extra="allow")
    app_name: str
    bundle_id: str
    platform: str
    version_hash: str = ""
    state_count: int = 0
    states: list = []


class AtlasStateDetail(BaseModel, LegacyDictMixin):
    """Detailed information about a specific UI state."""
    model_config = ConfigDict(extra="allow")
    state_id: str
    window_title: str | None = None
    elements: list = []


class AtlasAppInfo(BaseModel, LegacyDictMixin):
    """Lightweight info for a mapped app."""
    model_config = ConfigDict(extra="allow")
    app_name: str
    bundle_id: str
    platform: str


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
